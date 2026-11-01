"""Templates business operations; HTTP responses stay in api/."""

from ..db.migrations import initialize_templates_schema
from heteroes.catalog import SCHEDULER_POLICIES, SYNC_MODES, V3_DECODE_ENGINES
from heteroes.v3.options import validate_weight_space, validate_seed_namespace
from heteroes.v3.scoring import validate_spec
from datetime import datetime, timezone
import json
import uuid
from types import SimpleNamespace
from ..core.errors import ServiceError
from ..repositories.templates import TemplatesRepository as repository

MAX_PER_WORKSPACE = 50

INTEGERS = {
    "maxGenerations": (1, 1000),
    "candidatesPerGeneration": (2, 256),
    "recipeVersion": (1, 3),
    "validationInterval": (1, 1000),
    "batchSize": (1, 1024),
    "batchSeed": (0, 2**31),
    "maxNewTokens": (1, 2048),
    "momentumWindow": (2, 8),
    "evalChunk": (1, 64),
}

FLOATS = {
    "auditRate": (0, 1),
    "alpha": (1e-7, 1.0),
    "sigma": (1e-7, 1.0),
    "sigmaMinimum": (1e-7, 1.0),
    "alphaMinimum": (1e-7, 1.0),
    "momentumBeta": (1e-7, 0.9999999),
    "hardCapSeconds": (60, 7 * 86400),
    "stallSeconds": (30, 7 * 86400),
}

NULLABLE = {
    "alphaMinimum",
    "momentumBeta",
    "evalChunk",
    "hardCapSeconds",
    "stallSeconds",
}

CHOICES = {
    "schedulerPolicy": set(SCHEDULER_POLICIES),
    "syncMode": set(SYNC_MODES),
    "sigmaSchedule": {"constant", "cosine"},
    "decodeEngine": set(V3_DECODE_ENGINES),
    "coefficientRule": {"zscore@1", "centered-rank@1"},
    "alphaSchedule": {"constant", "cosine", "linear"},
    "sampler": {"sha256-python-random-sample-v1", "epoch-shuffle@1"},
}

SHORT_TEXT = {"task"}


def clean_config(config):
    """Validated settings, or ServiceError(422). Unknown keys are refused rather than silently dropped."""
    if not isinstance(config, dict) or not config:
        raise ServiceError(422, "A template needs at least one setting")
    known = (
        set(INTEGERS)
        | set(FLOATS)
        | set(CHOICES)
        | SHORT_TEXT
        | {"workerIds", "backupPolicy", "weightSpace", "antithetic", "scorer", "systemPrompt", "candidateSeedNamespace"}
    )
    unknown = sorted(set(config) - known)
    if unknown:
        raise ServiceError(422, f"Settings that cannot be saved in a template: {', '.join(unknown)}")
    result = {}
    for key, value in config.items():
        if key in NULLABLE and value is None:
            pass
        elif key in INTEGERS:
            low, high = INTEGERS[key]
            if type(value) is not int or not low <= value <= high:
                raise ServiceError(422, f"{key} must be a whole number from {low} to {high}")
        elif key in FLOATS:
            low, high = FLOATS[key]
            if type(value) not in (int, float) or not low <= value <= high:
                raise ServiceError(422, f"{key} must be a number from {low} to {high}")
        elif key in CHOICES:
            if not isinstance(value, str) or value not in CHOICES[key]:
                raise ServiceError(422, f"{key} has an unsupported value")
        elif key in SHORT_TEXT:
            if not isinstance(value, str) or not 1 <= len(value) <= 64:
                raise ServiceError(422, f"{key} must be a short text")
        elif key == "candidateSeedNamespace":
            try:
                validate_seed_namespace(value)
            except ValueError as error:
                raise ServiceError(422, str(error)) from None
        elif key in ("weightSpace", "scorer"):
            try:
                if key == "weightSpace":
                    validate_weight_space(value, initial_adapter=False)
                else:
                    validate_spec(value, allow_python=False)
            except (ValueError, TypeError) as error:
                raise ServiceError(422, str(error)) from None
        elif key == "antithetic":
            if type(value) is not bool:
                raise ServiceError(422, "Antithetic is true or false")
        elif key == "systemPrompt":
            if value is not None and (not isinstance(value, str) or not 1 <= len(value) <= 4000):
                raise ServiceError(422, "System prompt is null or a text of at most 4000 characters")
        elif key == "workerIds":
            if (
                not isinstance(value, list)
                or len(value) > 32
                or not all(isinstance(item, str) and 1 <= len(item) <= 100 for item in value)
            ):
                raise ServiceError(422, "workerIds must be a short list of names")
        elif key == "backupPolicy":
            if (
                not isinstance(value, dict)
                or set(value) != {"interval", "retain"}
                or any(type(v) is not int or not 1 <= v <= 1000 for v in value.values())
            ):
                raise ServiceError(422, "Backup interval and retention must be integers from 1 to 1000")
        result[key] = value
    return result


def operations(store, scoped):
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

    def list_templates(*, current):
        with store.db() as db:
            rows = repository.list_templates_select_experiment_templates(db, (current["workspaceId"],)).fetchall()
        return [present(row) for row in rows]

    def create_template(body: dict, *, current):
        name = body.get("name") if isinstance(body, dict) else None
        name = name.strip() if isinstance(name, str) else ""
        if not 3 <= len(name) <= 100:
            raise ServiceError(422, "The template name needs 3 to 100 characters")
        config = clean_config(body.get("config"))
        with store.db() as db:
            rows = repository.create_template_select_experiment_templates(db, (current["workspaceId"],)).fetchall()
            if len(rows) >= MAX_PER_WORKSPACE:
                raise ServiceError(422, f"A workspace can keep {MAX_PER_WORKSPACE} templates; delete one first")
            if any(row["name"].casefold() == name.casefold() for row in rows):
                raise ServiceError(409, "A template with this name already exists")
            row = {
                "id": uuid.uuid4().hex,
                "workspace_id": current["workspaceId"],
                "owner_id": current["userId"],
                "name": name,
                "config": json.dumps(config, sort_keys=True),
                "created": datetime.now(timezone.utc).isoformat(),
            }
            repository.create_template_insert_experiment_templates(db, row)
            store.audit(db, current["userId"], "TEMPLATE_CREATE", row["id"], current["workspaceId"])
        return present(row)

    def delete_template(template_id: str, *, current):
        with store.db() as db:
            row = repository.delete_template_select_experiment_templates(
                db, (template_id, current["workspaceId"])
            ).fetchone()
            if not row:
                raise ServiceError(404, "Template not found")
            if row["owner_id"] != current["userId"] and current["workspaceRole"] != "ADMIN":
                raise ServiceError(403, "Only the author or a workspace administrator can delete this template")
            repository.delete_template_delete_experiment_templates(db, (template_id,))
            store.audit(db, current["userId"], "TEMPLATE_DELETE", template_id, current["workspaceId"])
        return None

    return SimpleNamespace(
        present=present, list_templates=list_templates, create_template=create_template, delete_template=delete_template
    )
