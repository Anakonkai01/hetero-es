from contextlib import asynccontextmanager
import hashlib
import json
import os
from pathlib import Path
import secrets
import threading
import time

from argon2.exceptions import VerificationError
from fastapi import Depends, FastAPI, Header, HTTPException, Response
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from .store import ACTIVE, TERMINAL, Store, now
from .runtime import Runtime
from .lab import install_lab_routes


class Login(BaseModel):
    username: str = Field(max_length=100)
    password: str = Field(max_length=200)


class Configuration(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    name: str = Field(min_length=3, max_length=160)
    modelName: str
    modelArtifactId: str = "qwen-pinned"
    schedulerPolicy: str = "greedy"
    syncMode: str = "synchronous"
    workerIds: list[str] = Field(min_length=1, max_length=10)
    task: str = "arith16"
    maxGenerations: int = Field(default=3, ge=1, le=1000, strict=True)
    candidatesPerGeneration: int = Field(default=8, ge=2, le=256, strict=True)
    alpha: float = Field(default=.001, gt=0, le=1)
    sigma: float = Field(default=.001, gt=0, le=1)
    decodeEngine: str = "hf_generate"
    datasetIds: list[str] = Field(default_factory=list)


def create_app(path, passwords, runtime, dispatch=True):
    store = Store(path, passwords, runtime)
    stop = threading.Event()
    @asynccontextmanager
    async def lifespan(_):
        thread = threading.Thread(target=store.dispatch, args=(stop,), daemon=True)
        if dispatch:
            thread.start()
        yield
        stop.set()
        if dispatch:
            thread.join(timeout=2)
    app = FastAPI(title="HeteroES product API", lifespan=lifespan)
    app.state.store = store
    @app.exception_handler(HTTPException)
    async def handle_http(_request, error):
        return JSONResponse({"message": str(error.detail)}, status_code=error.status_code)

    def user(authorization: str = Header(default="")):
        if not authorization.startswith("Bearer "):
            raise HTTPException(401, "Sign in to continue")
        digest = hashlib.sha256(authorization[7:].encode()).hexdigest()
        with store.db() as db:
            row = db.execute("SELECT users.profile FROM sessions JOIN users ON users.id=sessions.user_id WHERE digest=? AND expires>?", (digest, time.time())).fetchone()
        if not row:
            raise HTTPException(401, "Session expired or revoked")
        return json.loads(row[0])

    def scoped(current=Depends(user), x_workspace_id: str = Header(default="")):
        profile = store.profile(current['userId'])
        if not profile or profile['accountStatus'] != 'ACTIVE':
            raise HTTPException(403, 'Your account must be active to access lab resources')
        membership = next((w for w in store.workspaces(current['userId']) if w['workspaceId']==x_workspace_id),None)
        if not membership:
            raise HTTPException(403, 'Select a workspace you belong to')
        return {**profile,'workspaceId':x_workspace_id,'workspaceRole':membership['role']}

    def session(current):
        return {"user": current, "workspaces": store.workspaces(current['userId']) if current['accountStatus']=='ACTIVE' else []}

    def visible(current):
        return [body for body in store.list() if not body.get("archivedAt") and
                body['workspaceId']==current['workspaceId'] and
                (current['workspaceRole']=='ADMIN' or body["ownerUserId"] == current["userId"])]

    def authorized(run_id, current):
        body = store.get(run_id)
        current = scoped(current,current['workspaceId'])
        if not body or body.get("archivedAt") or body['workspaceId']!=current['workspaceId'] or (current['workspaceRole'] != 'ADMIN' and body["ownerUserId"] != current["userId"]):
            raise HTTPException(404, "Experiment not found")
        return body

    def capabilities():
        try:
            value=runtime.capabilities()
            store.ensure_workers(value['workerIds'])
            return value
        except Exception:
            raise HTTPException(503, "Runtime control service unavailable") from None

    def validate(config, current):
        current = scoped(current,current['workspaceId'])
        cap = capabilities()
        body = config.model_dump()
        if body["modelName"] != cap["modelId"] or body["modelArtifactId"] != "qwen-pinned":
            raise HTTPException(422, "Only the pinned Qwen model is supported")
        if body["schedulerPolicy"] not in cap["schedulerPolicies"] or body["syncMode"] not in cap["syncModes"]:
            raise HTTPException(422, "Unsupported scheduling policy or synchronization mode")
        if body["task"] not in cap["workloads"] or body["decodeEngine"] not in ("hf_generate", "hf_compact") or body["datasetIds"]:
            raise HTTPException(422, "Select a built-in workload and decoder; dataset uploads are unavailable")
        if len(set(body["workerIds"])) != len(body["workerIds"]) or not set(body["workerIds"]) <= set(cap["workerIds"]):
            raise HTTPException(422, "Select configured workers without duplicates")
        if set(body["workerIds"]) & set(cap.get("quarantinedWorkerIds", [])):
            raise HTTPException(422, "Selected worker is quarantined after a restore mismatch")
        store.ensure_workers(cap['workerIds'])
        if not set(body['workerIds']) <= set(store.assignments(current['workspaceId'])):
            raise HTTPException(422, 'Select GPUs assigned to this workspace')
        return body

    @app.get("/api/v1/health")
    def health():
        return {"ok": True, "dataSource": "real", "runtimeIssue": store.last_error}

    @app.post("/api/v1/auth/login")
    def sign_in(body: Login):
        with store.db() as db:
            row = db.execute("SELECT id,hash,profile FROM users WHERE json_extract(profile,'$.username')=?", (body.username,)).fetchone()
            try:
                store.hasher.verify(row["hash"] if row else store.hasher.hash("unknown-user"), body.password)
            except VerificationError:
                raise HTTPException(401, "Invalid username or password") from None
            if not row:
                raise HTTPException(401, "Invalid username or password")
            token = secrets.token_urlsafe(32)
            db.execute("INSERT INTO sessions VALUES (?,?,?)", (hashlib.sha256(token.encode()).hexdigest(), row['id'], time.time()+43200))
            return {**session(json.loads(row["profile"])), "accessToken": token}

    @app.get("/api/v1/auth/session")
    def get_session(current=Depends(user)):
        return session(current)

    @app.post("/api/v1/auth/logout", status_code=204)
    def sign_out(current=Depends(user), authorization: str = Header()):
        with store.db() as db:
            db.execute("DELETE FROM sessions WHERE digest=?", (hashlib.sha256(authorization[7:].encode()).hexdigest(),))
        return Response(status_code=204)

    @app.get("/api/v1/workspaces")
    def workspaces(current=Depends(user)):
        return session(current)['workspaces']

    @app.get("/api/v1/capabilities")
    def get_capabilities(current=Depends(scoped)):
        cap=capabilities()
        assigned=set(store.assignments(current['workspaceId'],include_disabled=True))
        return {**cap,'workerIds':store.assignments(current['workspaceId']),
                'quarantinedWorkerIds':[w for w in cap.get('quarantinedWorkerIds',[]) if w in assigned]}

    @app.get("/api/v1/resources")
    def resources(current=Depends(scoped)):
        with store.db() as db:
            members = [{"user": {k:v for k,v in json.loads(row['profile']).items() if k not in ('platformAdmin','accountStatus')}, "role": row['role']}
                for row in db.execute('SELECT u.profile,m.role FROM memberships m JOIN users u ON u.id=m.user_id WHERE workspace_id=?',(current['workspaceId'],))]
        assigned = set(store.assignments(current['workspaceId'],include_disabled=True))
        enabled=set(store.assignments(current['workspaceId']))
        busy = list({worker for run in store.list() if run["status"] in ACTIVE for worker in run["workerIds"]} & assigned)
        return {"submissions": [], "invitations": [], "pools": [{"poolId": "shared", "workspaceId": current['workspaceId'],
                "name": "Workspace GPU pool", "workerIds": sorted(enabled), "drainingWorkerIds": sorted(set(busy)-enabled)}],
                "grants": [], "requests": [], "members": members, "busyWorkerIds": busy, "reservedWorkerIds": busy}

    @app.get("/api/v1/models")
    def models(current=Depends(scoped)):
        cap = capabilities()
        return [{"modelArtifactId": "qwen-pinned", "workspaceId": current['workspaceId'], "ownerUserId": "runtime", "name": cap["modelId"],
                 "reference": cap["modelId"], "revision": cap["modelRevision"], "source": "REFERENCE", "status": "REGISTERED"}]

    @app.get("/api/v1/workers")
    @app.get("/api/v1/worker-registry")
    def workers(current=Depends(scoped)):
        try:
            values = runtime.workers()
        except Exception:
            raise HTTPException(503, "Worker registry unavailable") from None
        # Shared GPU ownership is visible; another participant's experiment details are private.
        permitted = {body["experimentId"] for body in visible(current)}
        assigned = set(store.assignments(current['workspaceId'],include_disabled=True))
        enabled=set(store.assignments(current['workspaceId']))
        return [{**value,'contributionEnabled':value['workerId'] in enabled, "allocatedTo": value.get("allocatedTo") if value.get("allocatedTo") in permitted else
                 "Workspace pool busy" if value.get("allocatedTo") else None} for value in values if value['workerId'] in assigned]

    @app.get('/api/v1/my-workers')
    def owned_workers(current=Depends(user)):
        if current['accountStatus']!='ACTIVE':
            raise HTTPException(403,'Your account must be active to access GPU inventory')
        with store.db() as db:
            owned={r['worker_id']:r['workspace_id'] for r in db.execute('SELECT * FROM worker_assignments WHERE owner=?',(current['userId'],))}
        try:
            values=runtime.workers()
        except Exception:
            raise HTTPException(503,'Worker registry unavailable') from None
        return [{**value,'workspaceId':owned[value['workerId']],
                 'allocatedTo':'Owned GPU busy' if value.get('allocatedTo') else None}
                for value in values if value['workerId'] in owned]

    @app.get("/api/v1/workers/{worker_id}")
    def worker(worker_id: str, current=Depends(scoped)):
        value = next((value for value in workers(current) if value["workerId"] == worker_id), None)
        if not value:
            raise HTTPException(404, "Worker not found")
        return value

    @app.get("/api/v1/experiments")
    def experiments(current=Depends(scoped)):
        return visible(current)

    @app.post("/api/v1/experiments")
    def create(body: Configuration, current=Depends(scoped)):
        with store.lock:
            return store.create(current["userId"], validate(body,current),current['workspaceId'])

    @app.get("/api/v1/experiments/{run_id}")
    def experiment(run_id: str, current=Depends(scoped)):
        return authorized(run_id, current)

    @app.patch("/api/v1/experiments/{run_id}")
    def edit(run_id: str, request: dict, current=Depends(scoped)):
        with store.db() as db:
            old = authorized(run_id, current)
            if old["status"] != "DRAFT":
                raise HTTPException(409, "Submitted configuration is immutable")
            try:
                body = validate(Configuration(**request),current)
            except ValueError:
                raise HTTPException(422, "Invalid configuration") from None
            digest = hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
            old.update(**body, configHash=digest)
            store.save(db, old)
            store.audit(db, current["userId"], "EDIT", run_id,current['workspaceId'])
            return old

    @app.post("/api/v1/experiments/{run_id}/submit")
    def submit(run_id: str, current=Depends(scoped)):
        with store.db() as db:
            body = authorized(run_id, current)
            if body["status"] == "DRAFT":
                if json.loads(db.execute('SELECT value FROM settings WHERE key="dispatchHold"').fetchone()[0]):
                    raise HTTPException(409,'Submissions are held for maintenance or restored deployment review')
                if reason := store.eligibility(db,body):
                    raise HTTPException(409,reason)
                body["status"] = "QUEUED"
                db.execute("INSERT INTO queue(run_id) VALUES (?)", (run_id,))
                store.save(db, body)
                store.audit(db, current["userId"], "SUBMIT", run_id,current['workspaceId'])
            elif body["status"] in TERMINAL:
                raise HTTPException(409, "Experiment already finished")
            return body

    @app.post("/api/v1/experiments/{run_id}/cancel")
    def cancel(run_id: str, current=Depends(scoped)):
        with store.db() as db:
            body = authorized(run_id, current)
            if body["status"] in TERMINAL:
                return body
            body["cancelRequested"] = True
            if body["status"] in ("DRAFT", "QUEUED"):
                body.update(status="CANCELLED", completedAt=now())
                db.execute("DELETE FROM queue WHERE run_id=?", (run_id,))
            else:
                body["status"] = "CANCELLING"
            store.save(db, body)
            store.audit(db, current["userId"], "CANCEL", run_id,current['workspaceId'])
            return body

    @app.delete("/api/v1/experiments/{run_id}", status_code=204)
    def archive(run_id: str, current=Depends(scoped)):
        with store.db() as db:
            body = authorized(run_id, current)
            if body["status"] not in TERMINAL | {"DRAFT"}:
                raise HTTPException(409, "Cancel and wait for the experiment to finish before archiving")
            body["archivedAt"] = now()
            store.save(db, body)
            store.audit(db, current["userId"], "ARCHIVE", run_id,current['workspaceId'])
        return Response(status_code=204)

    @app.get("/api/v1/experiments/{run_id}/generations")
    def generations(run_id: str, current=Depends(scoped)):
        authorized(run_id, current)
        return store.snapshot(run_id)["generations"]

    @app.get("/api/v1/experiments/{run_id}/generations/{generation_id}")
    def generation(run_id: str, generation_id: str, current=Depends(scoped)):
        value = next((value for value in generations(run_id, current) if value["generationId"] == generation_id), None)
        if not value:
            raise HTTPException(404, "Generation not found")
        return value

    def lookup(identifier, key, collection, current):
        run_id = identifier.split(".", 1)[0]
        authorized(run_id, current)
        value = next((item for item in store.snapshot(run_id)[collection] if item[key] == identifier), None)
        if not value:
            raise HTTPException(404, "Object not found")
        return value

    @app.get("/api/v1/generations/{generation_id}/candidates")
    def candidates(generation_id: str, current=Depends(scoped)):
        run_id = generation_id.split(".", 1)[0]
        authorized(run_id, current)
        return [item for item in store.snapshot(run_id)["candidates"] if item["generationId"] == generation_id]

    @app.get("/api/v1/candidates/{candidate_id}")
    def candidate(candidate_id: str, current=Depends(scoped)):
        return lookup(candidate_id, "candidateId", "candidates", current)

    @app.get("/api/v1/attempts/{attempt_id}")
    def attempt(attempt_id: str, current=Depends(scoped)):
        return lookup(attempt_id, "attemptId", "attempts", current)

    @app.get("/api/v1/events")
    def event_list(current=Depends(scoped)):
        from datetime import datetime, timezone
        result = []
        for run in visible(current):
            for index, event in enumerate(store.snapshot(run["experimentId"])["events"]):
                result.append({"eventId": f"{run['experimentId']}.e{index}", "experimentId": run["experimentId"],
                    "timestamp": datetime.fromtimestamp(event.get("t", 0), timezone.utc).isoformat(),
                    "eventType": event["event"], "severity": "ERROR" if "error" in event["event"] else
                    "WARNING" if "unavailable" in event["event"] or "unknown" in event["event"] else "INFO",
                    "message": event.get("error", event["event"].replace("_", " ")), "workerId": event.get("worker_id"),
                    "candidateId": event.get("uiCandidateId"),
                    "generationId": f"{run['experimentId']}.g{event['generation']}" if "generation" in event else None,
                    "details": event})
        return sorted(result, key=lambda item: item["timestamp"])[-2000:]

    @app.get("/api/v1/artifacts")
    def artifact_list(current=Depends(scoped)):
        return [item for run in visible(current) for item in store.snapshot(run["experimentId"])["artifacts"]]

    @app.get("/api/v1/artifacts/{artifact_id}/download")
    def download(artifact_id: str, current=Depends(scoped)):
        artifact = lookup(artifact_id, "artifactId", "artifacts", current)
        return StreamingResponse(runtime.artifact(artifact["experimentId"], artifact["name"]),
            media_type="application/octet-stream", headers={"Content-Disposition": f'attachment; filename="{artifact["name"]}"'})

    @app.get("/api/v1/audit")
    def audit(current=Depends(scoped)):
        with store.db() as db:
            return [{"auditId": str(row["sequence"]), "workspaceId": row['workspace_id'], "actorUserId": row["actor"],
                    "action": row["action"], "targetId": row["target"], "createdAt": row["created"]}
                    for row in db.execute("SELECT * FROM audit WHERE workspace_id=? ORDER BY sequence DESC LIMIT 100",(current['workspaceId'],))
                    if current['workspaceRole']=='ADMIN' or row["actor"] == current["userId"]]

    @app.get("/api/v1/datasets")
    @app.get("/api/v1/my-resource-submissions")
    def empty(current=Depends(scoped)):
        return []

    install_lab_routes(app,store,user,scoped,runtime)

    @app.api_route("/api/v1/{unsupported:path}", methods=["POST", "PATCH", "DELETE"])
    def unavailable(unsupported: str, current=Depends(scoped)):
        raise HTTPException(501, "This operation is unavailable in the current runtime integration")
    return app


def app_from_environment():
    root = Path(os.environ.get("HETEROES_PRIVATE_CONFIG", str(Path.home() / ".config/heteroes-integration")))
    credentials = json.loads((root / "credentials.json").read_text())
    config = json.loads((root / "config.json").read_text())
    runtime = Runtime("http://127.0.0.1:" + str(config.get("controlPort", 8766)), credentials["runtime_token"])
    return create_app(Path(config["productStateDirectory"]) / "product.sqlite", credentials["users"], runtime)
