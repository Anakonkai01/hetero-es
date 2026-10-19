"""Saved experiment settings ("templates") of a workspace.

A template holds only plain settings (sizes, rates, decoder, GPU names), never model, dataset or device ids, which can go
stale; the experiment wizard still validates everything when a run is created from it.
"""

from .migrations import initialize_templates_schema
from datetime import datetime, timezone
import json
import uuid

from fastapi import Depends, HTTPException, Response

MAX_PER_WORKSPACE = 50
INTEGERS = {
    "maxGenerations": (1, 1000),
    "candidatesPerGeneration": (2, 256),
    "recipeVersion": (1, 2),
    "batchSize": (1, 1024),
    "batchSeed": (0, 2**31),
    "maxNewTokens": (1, 2048),
}
FLOATS = {"alpha": (1e-7, 1.0), "sigma": (1e-7, 1.0), "sigmaMinimum": (1e-7, 1.0)}
CHOICES = {
    "schedulerPolicy": {"capacity-weighted", "round-robin", "greedy"},
    "syncMode": {"synchronous", "asynchronous"},
    "sigmaSchedule": {"constant", "cosine"},
    "decodeEngine": {"hf_generate", "hf_compact"},
}
SHORT_TEXT = {"task"}


def clean_config(config):
    """Validated settings, or HTTPException(422). Unknown keys are refused rather than silently dropped."""
    if not isinstance(config, dict) or not config:
        raise HTTPException(422, "A template needs at least one setting")
    known = set(INTEGERS) | set(FLOATS) | set(CHOICES) | SHORT_TEXT | {"workerIds", "backupPolicy"}
    unknown = sorted(set(config) - known)
    if unknown:
        raise HTTPException(422, f"Settings that cannot be saved in a template: {', '.join(unknown)}")
    result = {}
    for key, value in config.items():
        if key in INTEGERS:
            low, high = INTEGERS[key]
            if type(value) is not int or not low <= value <= high:
                raise HTTPException(422, f"{key} must be a whole number from {low} to {high}")
        elif key in FLOATS:
            low, high = FLOATS[key]
            if type(value) not in (int, float) or not low <= value <= high:
                raise HTTPException(422, f"{key} must be a number from {low} to {high}")
        elif key in CHOICES:
            if not isinstance(value, str) or value not in CHOICES[key]:
                raise HTTPException(422, f"{key} has an unsupported value")
        elif key in SHORT_TEXT:
            if not isinstance(value, str) or not 1 <= len(value) <= 64:
                raise HTTPException(422, f"{key} must be a short text")
        elif key == "workerIds":
            if (
                not isinstance(value, list)
                or len(value) > 32
                or not all(isinstance(item, str) and 1 <= len(item) <= 100 for item in value)
            ):
                raise HTTPException(422, "workerIds must be a short list of names")
        elif key == "backupPolicy":
            if (
                not isinstance(value, dict)
                or set(value) != {"interval", "retain"}
                or any(type(v) is not int or not 1 <= v <= 1000 for v in value.values())
            ):
                raise HTTPException(422, "Backup interval and retention must be integers from 1 to 1000")
        result[key] = value
    return result


def install_template_routes(app, store, scoped):
    with store.db() as db:
        initialize_templates_schema(db)

    def present(row):
        owner = store.profile(row["owner_id"]) or {}
        return {
            "templateId": row["id"],
            "name": row["name"],
            "config": json.loads(row["config"]),
            "ownerUserId": row["owner_id"],
            "ownerName": owner.get("displayName", ""),
            "created": row["created"],
        }

    @app.get("/api/v1/experiment-templates")
    def list_templates(current=Depends(scoped)):
        with store.db() as db:
            rows = db.execute(
                "SELECT * FROM experiment_templates WHERE workspace_id=? ORDER BY created DESC, id",
                (current["workspaceId"],),
            ).fetchall()
        return [present(row) for row in rows]

    @app.post("/api/v1/experiment-templates", status_code=201)
    def create_template(body: dict, current=Depends(scoped)):
        name = body.get("name") if isinstance(body, dict) else None
        name = name.strip() if isinstance(name, str) else ""
        if not 3 <= len(name) <= 100:
            raise HTTPException(422, "The template name needs 3 to 100 characters")
        config = clean_config(body.get("config"))
        with store.db() as db:
            rows = db.execute(
                "SELECT name FROM experiment_templates WHERE workspace_id=?", (current["workspaceId"],)
            ).fetchall()
            if len(rows) >= MAX_PER_WORKSPACE:
                raise HTTPException(422, f"A workspace can keep {MAX_PER_WORKSPACE} templates; delete one first")
            if any(row["name"].casefold() == name.casefold() for row in rows):
                raise HTTPException(409, "A template with this name already exists")
            row = {
                "id": uuid.uuid4().hex,
                "workspace_id": current["workspaceId"],
                "owner_id": current["userId"],
                "name": name,
                "config": json.dumps(config, sort_keys=True),
                "created": datetime.now(timezone.utc).isoformat(),
            }
            db.execute(
                "INSERT INTO experiment_templates VALUES (:id,:workspace_id,:owner_id,:name,:config,:created)", row
            )
            store.audit(db, current["userId"], "TEMPLATE_CREATE", row["id"], current["workspaceId"])
        return present(row)

    @app.delete("/api/v1/experiment-templates/{template_id}", status_code=204)
    def delete_template(template_id: str, current=Depends(scoped)):
        with store.db() as db:
            row = db.execute(
                "SELECT * FROM experiment_templates WHERE id=? AND workspace_id=?",
                (template_id, current["workspaceId"]),
            ).fetchone()
            if not row:
                raise HTTPException(404, "Template not found")
            if row["owner_id"] != current["userId"] and current["workspaceRole"] != "ADMIN":
                raise HTTPException(403, "Only the author or a workspace administrator can delete this template")
            db.execute("DELETE FROM experiment_templates WHERE id=?", (template_id,))
            store.audit(db, current["userId"], "TEMPLATE_DELETE", template_id, current["workspaceId"])
        return Response(status_code=204)
