from .policies import storage_status
from .config import load_config
import json
import os

from fastapi import Depends, HTTPException

from .store import ACTIVE









from fastapi import APIRouter


def install_routes(app, store, runtime, scoped, visible, capabilities, registry):
    router = APIRouter()
    @router.get("/api/v1/health")
    def health():
        ui_url=os.environ.get('HETEROES_UI_URL')
        config={}
        private_root=os.environ.get('HETEROES_PRIVATE_CONFIG')
        if private_root:
            # Quick URLs can rotate while this CPU service retains its identity.
            try:
                config=load_config(private_root)
                ui_url=config.get('publicWebUrl') or ui_url
            except (OSError,ValueError):
                pass
        backend=getattr(runtime,'storage_backend',None)
        return {"ok": True, "dataSource": "real", "runtimeIssue": store.last_error,
                # Shipped r10 apps require these protocol capability fields.
                "agentMode":True,
                'deviceConfiguration':True,
                'recipeVersions':[1,2],
                **storage_status(runtime),
                "serverInstanceId":getattr(runtime,'server_instance_id',None),
                **({"uiUrl":ui_url} if ui_url else {}),
                **({'privateLabUrl':config.get('bulkApiUrl',config['apiUrl'])} if config.get('apiUrl') else {})}

    @router.get("/api/v1/capabilities")
    def get_capabilities(current=Depends(scoped)):
        cap=capabilities()
        assigned=set(store.assignments(current['workspaceId'],include_disabled=True))
        return {**cap,'workerIds':store.assignments(current['workspaceId']),
                'coordinatorDevices':[{'deviceId':d['deviceId'],'workerId':d['workerId']} for d in runtime.devices() if d['workspaceId']==current['workspaceId'] and d['approvalStatus']=='APPROVED' and d['selfTest']['coordinator']],
                'quarantinedWorkerIds':[w for w in cap.get('quarantinedWorkerIds',[]) if w in assigned]}

    @router.get("/api/v1/resources")
    def resources(current=Depends(scoped)):
        with store.db() as db:
            members = [{"user": {k:v for k,v in json.loads(row['profile']).items() if k not in ('platformAdmin','accountStatus')}, "role": row['role']}
                for row in db.execute('SELECT u.profile,m.role FROM memberships m JOIN users u ON u.id=m.user_id WHERE workspace_id=?',(current['workspaceId'],))]
        assigned = set(store.assignments(current['workspaceId'],include_disabled=True))
        busy = list({worker for run in store.list() if run["status"] in ACTIVE for worker in run["workerIds"]} & assigned)
        return {"members": members, "busyWorkerIds": busy, "reservedWorkerIds": busy}

    @router.get("/api/v1/models")
    def models(current=Depends(scoped)):
        cap = capabilities()
        return [{"modelArtifactId": "qwen-pinned", "workspaceId": current['workspaceId'], "ownerUserId": "runtime", "name": cap["modelId"],
                 "reference": cap["modelId"], "revision": cap["modelRevision"], "source": "REFERENCE", "status": "REGISTERED"}]+registry.list(current['workspaceId'],'model')

    @router.get("/api/v1/workers")
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

    @router.get("/api/v1/workers/{worker_id}")
    def worker(worker_id: str, current=Depends(scoped)):
        value = next((value for value in workers(current) if value["workerId"] == worker_id), None)
        if not value:
            raise HTTPException(404, "Worker not found")
        return value

    @router.get("/api/v1/datasets")
    def datasets(current=Depends(scoped)):
        return registry.list(current['workspaceId'],'dataset')

    app.include_router(router)
