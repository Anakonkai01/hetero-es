"""Devices HTTP adapters."""

from ..core.device_models import (
    EndpointUpdate,
    DeviceConfigurationUpdate,
    QualificationUpdate,
    Enrollment,
    Approval,
    Contribution,
    DeviceContribution,
    ContributionPreference,
    DeviceName,
    Poll,
    WorkerCommand,
)
from fastapi import Depends, Header, HTTPException, Request
from fastapi import Response
from fastapi import APIRouter
from ..services.devices import operations


def install_routes(app, store, user, runtime):
    service = operations(store, user, runtime)
    router = APIRouter()

    def device_auth(request: Request, authorization: str = Header(default="")):
        if not authorization.startswith("Bearer "):
            raise HTTPException(401, "Device authentication required")
        path = request.url.path
        purpose = (
            "poll"
            if path == "/api/v1/device/poll"
            else "worker-command"
            if path == "/api/v1/device/worker-command"
            else "control"
        )
        return service.authenticate_device(authorization[7:], purpose)

    def admin(current=Depends(user)):
        return service.admin(current=current)

    @app.post("/api/v1/devices/pairing-codes")
    def pairing(current=Depends(user)):
        return service.pairing(current=current)

    @app.post("/api/v1/device/enroll", status_code=201)
    def enroll(body: Enrollment):
        return service.enroll(body=body)

    @app.get("/api/v1/devices")
    def own_devices(current=Depends(user)):
        return service.own_devices(current=current)

    @app.patch("/api/v1/devices/{device_id}/endpoints")
    def owned_endpoints(device_id: str, body: EndpointUpdate, current=Depends(user)):
        return service.owned_endpoints(device_id=device_id, body=body, current=current)

    @app.patch("/api/v1/devices/{device_id}/configuration")
    def owned_configuration(device_id: str, body: DeviceConfigurationUpdate, current=Depends(user)):
        return service.owned_configuration(device_id=device_id, body=body, current=current)

    @app.patch("/api/v1/device/qualification")
    def qualification(body: QualificationUpdate, current=Depends(device_auth)):
        return service.qualification(body=body, current=current)

    @app.get("/api/v1/platform/devices")
    def devices(current=Depends(admin)):
        return service.devices(current=current)

    @app.patch("/api/v1/platform/devices/{device_id}")
    def approve(device_id: str, body: Approval, current=Depends(admin)):
        return service.approve(device_id=device_id, body=body, current=current)

    @app.delete("/api/v1/platform/devices/{device_id}", status_code=204)
    def remove_device(device_id: str, current=Depends(admin)):
        service.remove_device(device_id=device_id, current=current)
        return Response(status_code=204)

    @app.patch("/api/v1/devices/{device_id}")
    def rename(device_id: str, body: DeviceName, current=Depends(user)):
        return service.rename(device_id=device_id, body=body, current=current)

    @app.delete("/api/v1/devices/{device_id}", status_code=204)
    def delete_device(device_id: str, current=Depends(user)):
        """Revoke and remove in one step (owner 2026-10-22): its credential stops working and it leaves every list.
        Never while a run holds it, which would cancel that run: it is turned OFF or the run ends first."""
        service.delete_device(device_id=device_id, current=current)
        return Response(status_code=204)

    @app.post("/api/v1/devices/{device_id}/contribution")
    def contribution(device_id: str, body: Contribution, current=Depends(user)):
        return service.contribution(device_id=device_id, body=body, current=current)

    @app.patch("/api/v1/devices/{device_id}/contribution")
    def contribution_preference(device_id: str, body: ContributionPreference, current=Depends(user)):
        return service.contribution_preference(device_id=device_id, body=body, current=current)

    @app.post("/api/v1/device/contribution")
    def own_contribution(body: DeviceContribution, current=Depends(device_auth)):
        return service.own_contribution(body=body, current=current)

    @app.patch("/api/v1/device/name")
    def own_name(body: DeviceName, current=Depends(device_auth)):
        return service.own_name(body=body, current=current)

    @app.delete("/api/v1/device", status_code=204)
    def forget_self(current=Depends(device_auth)):
        """The machine leaves the lab (`heteroes-worker forget`): its token stops working. Never while it holds work."""
        service.forget_self(current=current)
        return Response(status_code=204)

    @app.get("/api/v1/device/summary")
    def own_summary(current=Depends(device_auth)):
        """What the machine's command line shows: its name, approval, contribution and the run it takes part in."""
        return service.own_summary(current=current)

    @app.post("/api/v1/device/poll")
    def poll(
        body: Poll,
        current=Depends(device_auth),
        capabilities: str | None = Header(default=None, alias="X-HeteroES-Agent-Commands"),
    ):
        return service.poll(body=body, current=current, capabilities=capabilities)

    @app.post("/api/v1/device/worker-command")
    def worker(body: WorkerCommand, current=Depends(device_auth)):
        return service.worker(body=body, current=current)

    app.include_router(router)
    return device_auth
