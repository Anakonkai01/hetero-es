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
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

from .store import ACTIVE, TERMINAL, Store, now
from .runtime import Runtime
from .lab import install_lab_routes


class Login(BaseModel):
    username: str = Field(max_length=100)
    password: str = Field(max_length=200)


class BackupPolicy(BaseModel):
    model_config=ConfigDict(extra='forbid')
    interval:int=Field(ge=1,le=1000,strict=True)
    retain:int=Field(ge=1,le=1000,strict=True)


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
    coordinatorDeviceId: str | None = None
    backupPolicy: dict | None = None
    recipeVersion: int = Field(default=1,ge=1,le=2,strict=True)
    batchSize: int = Field(default=32,ge=1,le=1024,strict=True)
    batchSeed: int = Field(default=11,ge=0,lt=2**53,strict=True)
    sigmaSchedule: str = 'constant'
    sigmaMinimum: float = Field(default=.00025,gt=0,le=1)
    maxNewTokens: int = Field(default=512,ge=1,le=2048,strict=True)
    validationInterval: int = Field(default=1,ge=1,le=1000,strict=True)


def create_app(path, passwords, runtime, dispatch=True, web_directory=None, downloads_directory=None):
    store = Store(path, passwords, runtime)
    from .study_registry import Registry
    registry=Registry(store)
    stop = threading.Event()
    @asynccontextmanager
    async def lifespan(_):
        thread = threading.Thread(target=store.dispatch, args=(stop,), daemon=True)
        if dispatch:
            thread.start()
        metadata_thread=None
        if getattr(runtime,'storage_backend',None) is not None:
            from .cloud_metadata import backup_loop
            metadata_thread=threading.Thread(target=backup_loop,args=(store,app.state.storage,stop),daemon=True)
            metadata_thread.start()
        yield
        stop.set()
        if metadata_thread:metadata_thread.join(timeout=2)
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
        if getattr(runtime, 'agent_mode', False):
            co = next((d for d in runtime.devices() if d['deviceId']==body['coordinatorDeviceId']),None)
            if not co or co['approvalStatus']!='APPROVED' or co['workspaceId']!=current['workspaceId'] or not co['selfTest']['coordinator']:
                raise HTTPException(422, 'Select an approved coordinator in this workspace')
            policy=body.get('backupPolicy') or {'interval':1,'retain':3}
            if set(policy)!={'interval','retain'} or any(type(v) is not int or not 1<=v<=1000 for v in policy.values()):
                raise HTTPException(422, 'Backup interval and retention must be integers from 1 to 1000')
            body['backupPolicy']=policy
        else:
            if body['coordinatorDeviceId'] is not None or body['backupPolicy'] is not None:
                raise HTTPException(422, 'Agent settings require agent deployment mode')
            body.pop('coordinatorDeviceId'); body.pop('backupPolicy')
        if body['recipeVersion']==2:
            if not getattr(runtime,'agent_mode',False):raise HTTPException(422,'Recipe v2 requires device agents')
            model=registry.get(body['modelArtifactId'],current['workspaceId'],'model')
            if model['status'] not in ('READY','REGISTERED') or model['reference']!=body['modelName']:raise HTTPException(422,'Model is unavailable or its name differs')
            if len(body['datasetIds'])!=1:raise HTTPException(422,'Select one frozen dataset')
            data=registry.get(body['datasetIds'][0],current['workspaceId'],'dataset')
            if body['batchSize']>data['counts']['train'] or body['sigmaSchedule'] not in ('constant','cosine') or body['sigmaMinimum']>body['sigma']:
                raise HTTPException(422,'Invalid batch size or sigma schedule')
            if body['task']!='text_math_v2' or body['decodeEngine']!='hf_generate':raise HTTPException(422,'Recipe v2 uses exact math and the HF decoder')
            selected=[d for d in runtime.devices() if d['deviceId']==body['coordinatorDeviceId'] or d['workerId'] in body['workerIds']]
            for d in selected:
                profile=d['selfTest']
                if profile.get('platform')=='windows' or 2 not in profile.get('recipeVersions',[]):raise HTTPException(422,'Selected device requires Recipe v2 qualification; Windows remains v1 worker-only')
                if model['manifestHash'] not in profile.get('qualifiedModelHashes',[]):raise HTTPException(422,'Qualify every selected device for this pinned model')
            body.update(modelManifest=model['manifest'],modelSource=model['source'],datasetObjectSha256=data['objectSha256'],datasetIdentity=data['identity'])
        else:
            if body["modelName"] != cap["modelId"] or body["modelArtifactId"] != "qwen-pinned":
                raise HTTPException(422, "Only the pinned Qwen model is supported for Recipe v1")
            if body["task"] not in cap["workloads"] or body["decodeEngine"] not in ("hf_generate", "hf_compact") or body["datasetIds"]:
                raise HTTPException(422, "Select a built-in workload and decoder for Recipe v1")
            for key in ('recipeVersion','batchSize','batchSeed','sigmaSchedule','sigmaMinimum','maxNewTokens','validationInterval'):
                body.pop(key)
        if body["schedulerPolicy"] not in cap["schedulerPolicies"] or body["syncMode"] not in cap["syncModes"]:
            raise HTTPException(422, "Unsupported scheduling policy or synchronization mode")
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
        ui_url=os.environ.get('HETEROES_UI_URL')
        config={}
        private_root=os.environ.get('HETEROES_PRIVATE_CONFIG')
        if private_root:
            # Quick URLs can rotate while this CPU service retains its identity.
            try:
                config=json.loads((Path(private_root)/'config.json').read_text())
                ui_url=config.get('publicWebUrl') or ui_url
            except (OSError,ValueError):
                pass
        backend=getattr(runtime,'storage_backend',None)
        return {"ok": True, "dataSource": "real", "runtimeIssue": store.last_error,
                "agentMode":bool(getattr(runtime,"agent_mode",False)),
                'recipeVersions':[1,2] if getattr(runtime,'agent_mode',False) else [1],
                "cloudStorageConfigured":backend is not None and getattr(backend,'mode','cloud')=='cloud',
                "recoveryStorageConfigured":backend is not None,
                "recoveryStorageMode":getattr(backend,'mode','cloud') if backend else None,
                "serverInstanceId":getattr(runtime,'server_instance_id',None),
                **({"uiUrl":ui_url} if ui_url else {}),
                **({'privateLabUrl':config.get('bulkApiUrl',config['apiUrl'])} if config.get('apiUrl') else {})}

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
                'coordinatorDevices':[{'deviceId':d['deviceId'],'workerId':d['workerId']} for d in runtime.devices() if d['workspaceId']==current['workspaceId'] and d['approvalStatus']=='APPROVED' and d['selfTest']['coordinator']] if getattr(runtime,'agent_mode',False) else [],
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
                 "reference": cap["modelId"], "revision": cap["modelRevision"], "source": "REFERENCE", "status": "REGISTERED"}]+registry.list(current['workspaceId'],'model')

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
        return [{**value,'contributionEnabled':value['workerId'] in enabled and value.get('contributionEnabled',True), "allocatedTo": value.get("allocatedTo") if value.get("allocatedTo") in permitted else
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
            if body["status"] in ("DRAFT", "QUEUED", "PAUSED"):
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
    def datasets(current=Depends(scoped)):
        return registry.list(current['workspaceId'],'dataset')

    @app.get("/api/v1/my-resource-submissions")
    def empty(current=Depends(scoped)):
        return []

    if getattr(runtime,'agent_mode',False):
        @app.post('/api/v1/experiments/{run_id}/pause')
        def pause(run_id:str,current=Depends(scoped)):
            with store.db() as db:
                db.execute('BEGIN IMMEDIATE')
                body=authorized(run_id,current)
                if body['status']=='PAUSED':return body
                if body.get('cancelRequested') or body['status'] not in ('STARTING','RUNNING','PAUSING'):
                    raise HTTPException(409,'Pause requires a running experiment')
                body.update(pauseRequested=True,status='PAUSING')
                store.save(db,body)
                store.audit(db,current['userId'],'PAUSE_REQUESTED',run_id,body['workspaceId'])
            runtime.pause(run_id)
            return body

        @app.post('/api/v1/experiments/{run_id}/resume')
        def resume(run_id:str,current=Depends(scoped)):
            with store.db() as db:
                db.execute('BEGIN IMMEDIATE')
                body=authorized(run_id,current)
                if body.get('resumeRequested') and body['status'] in ('QUEUED','STARTING'):return body
                row=db.execute('SELECT released,snapshot FROM assignments WHERE run_id=? ORDER BY epoch DESC LIMIT 1',(run_id,)).fetchone()
                if body['status']!='PAUSED' or not row or not row['released'] or json.loads(row['snapshot'])['state']['status']!='PAUSED':
                    raise HTTPException(409,'Wait for the completed checkpoint and confirmed resource release')
                if reason:=store.eligibility(db,body):raise HTTPException(409,reason)
                body.update(status='QUEUED',resumeRequested=True,pauseRequested=False,cancelRequested=False)
                body.pop('waitingReason',None)
                store.save(db,body)
                db.execute('INSERT OR IGNORE INTO queue(run_id) VALUES (?)',(run_id,))
                store.audit(db,current['userId'],'RESUME_REQUESTED',run_id,body['workspaceId'])
            return body

        @app.patch('/api/v1/experiments/{run_id}/backup-policy')
        def backup_policy(run_id:str,policy:BackupPolicy,current=Depends(scoped)):
            with store.db() as db:
                body=authorized(run_id,current)
                if body['status'] in TERMINAL:raise HTTPException(409,'Experiment is already finished')
                body['requestedBackupPolicy']=policy.model_dump()
                store.save(db,body)
                assignment=db.execute('SELECT id,coordinator,epoch,released FROM assignments WHERE run_id=? ORDER BY epoch DESC LIMIT 1',(run_id,)).fetchone()
                if assignment and not assignment['released']:
                    runtime._enqueue(db,assignment['coordinator'],'UPDATE_BACKUP_POLICY',{'assignmentId':assignment['id'],'epoch':assignment['epoch'],'policy':policy.model_dump()},'backup-policy:'+secrets.token_hex(16))
                store.audit(db,current['userId'],'BACKUP_POLICY_REQUESTED',run_id,body['workspaceId'])
            return {'policy':policy.model_dump(),'appliesBeforeNextGeneration':True}

        @app.get('/api/v1/experiments/{run_id}/monitoring-events')
        def monitoring_events(run_id:str,afterSequence:int=0,current=Depends(scoped)):
            authorized(run_id,current)
            with store.db() as db:
                return [{'sequence':r['sequence'],'eventId':r['event_id'],'event':json.loads(r['body'])} for r in db.execute(
                    'SELECT e.* FROM monitoring_events e JOIN assignments a ON a.id=e.assignment_id WHERE a.run_id=? AND e.sequence>? ORDER BY e.sequence LIMIT 2000',(run_id,max(0,afterSequence)))]

    install_lab_routes(app,store,user,scoped,runtime)
    if getattr(runtime, 'agent_mode', False):
        from .devices import install_device_routes
        device_auth=install_device_routes(app,store,user,runtime)
        from .study_registry import install_routes as study_routes
        study_routes(app,registry,runtime,scoped,device_auth)
        if runtime.storage_backend is not None:
            from .cloud_storage import CloudStorage, install_storage_routes
            storage=CloudStorage(store,runtime.storage_backend,
                quota_bytes=getattr(runtime.storage_backend,'quota_bytes',8_000_000_000))
            app.state.storage=storage
            runtime.storage=storage
            install_storage_routes(app,store,storage,device_auth,user,scoped,authorized)
            if hasattr(runtime.storage_backend,'install_routes'):
                runtime.storage_backend.install_routes(app)

    @app.api_route("/api/v1/{unsupported:path}", methods=["POST", "PATCH", "DELETE"])
    def unavailable(unsupported: str, current=Depends(scoped)):
        raise HTTPException(501, "This operation is unavailable in the current runtime integration")
    if web_directory is not None:
        web = Path(web_directory).resolve(strict=True)
        if not (web / 'index.html').is_file():
            raise ValueError('Built web application is missing')
        app.mount('/assets', StaticFiles(directory=web / 'assets'), name='web-assets')
        if downloads_directory is not None:
            @app.get('/downloads/manifest.json',include_in_schema=False)
            def installer_manifest():
                manifest=json.loads((Path(downloads_directory)/'manifest.json').read_text())
                private_root=os.environ.get('HETEROES_PRIVATE_CONFIG')
                if private_root:
                    config=json.loads((Path(private_root)/'config.json').read_text())
                    # publicDownloads: the operator serves installers on the public origin too.
                    if config.get('publicWebUrl') and not config.get('publicDownloads'):
                        bulk=config.get('bulkApiUrl',config.get('apiUrl'))
                        manifest['privateTransferRequired']=True
                        for group in ('installers','serverInstallers'):
                            for item in manifest.get(group,[]):
                                item['url']=bulk+'/downloads/'+Path(item['name']).name
                return manifest
            # The publisher links installers from another disk; Starlette refuses such symlinks by default.
            # Path traversal is still rejected: the check then compares the link's own location.
            app.mount('/downloads',StaticFiles(directory=downloads_directory,follow_symlink=True),name='worker-downloads')
        else:
            @app.get('/downloads/manifest.json',include_in_schema=False)
            def no_installers():
                return {'version':'0.1.0','privateTrial':True,'installers':[]}

        @app.get('/{route:path}', include_in_schema=False)
        def web_page(route: str):
            if route == 'api' or route.startswith(('api/', 'assets/', 'downloads/')):
                raise HTTPException(404, 'Unknown endpoint')
            candidate = web / route
            if candidate.is_file() and candidate.resolve().is_relative_to(web):
                return FileResponse(candidate)
            return FileResponse(web / 'index.html', headers={'Cache-Control':'no-cache'})
    return app


def app_from_environment():
    root = Path(os.environ.get("HETEROES_PRIVATE_CONFIG", str(Path.home() / ".config/heteroes-integration")))
    credentials = json.loads((root / "credentials.json").read_text())
    config = json.loads((root / "config.json").read_text())
    if config.get('deploymentMode') == 'agent':
        from .devices import AgentRuntime
        storage_backend=None
        if config.get('storageMode') == 'local':
            from .local_storage import LocalBackend
            storage_backend=LocalBackend(config['storageDirectory'],root/'storage-signing.key',config.get('bulkApiUrl',config['apiUrl']),config.get('storageVolumeUUID'),config.get('metadataStorageDirectory'))
            storage_backend.quota_bytes=config.get('storageQuotaBytes',200_000_000_000)
        elif config.get('storageFile'):
            from .cloud_storage import S3Backend
            storage_backend=S3Backend(json.loads(Path(config['storageFile']).read_text()))
        runtime = AgentRuntime(storage_backend)
    else:
        runtime = Runtime("http://127.0.0.1:" + str(config.get("controlPort", 8766)), credentials["runtime_token"])
    runtime.server_instance_id=config.get('serverInstanceId')
    return create_app(Path(config["productStateDirectory"]) / "product.sqlite", credentials["users"], runtime,
                      web_directory=os.environ.get('HETEROES_WEB_DIRECTORY'),
                      downloads_directory=os.environ.get('HETEROES_DOWNLOADS_DIRECTORY'))
