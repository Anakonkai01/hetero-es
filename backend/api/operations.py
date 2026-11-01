"""Operations HTTP adapters."""

from ..core.request_models import AccountEdit, Resume
from fastapi import Depends, Response
from fastapi import APIRouter
from ..services.operations import operations as business_operations


def install_routes(app, store, runtime, platform):
    service = business_operations(store, runtime, platform)
    router = APIRouter()

    @router.get("/api/v1/platform/users")
    def users(current=Depends(platform)):
        return service.users(current=current)

    @router.patch("/api/v1/platform/users/{user_id}")
    def edit_account(user_id: str, body: AccountEdit, current=Depends(platform)):
        return service.edit_account(user_id=user_id, body=body, current=current)

    @router.post("/api/v1/platform/users/{user_id}/revoke-sessions", status_code=204)
    def revoke_sessions(user_id: str, current=Depends(platform)):
        service.revoke_sessions(user_id=user_id, current=current)
        return Response(status_code=204)

    @router.get("/api/v1/platform/audit")
    def platform_audit(current=Depends(platform)):
        return service.platform_audit(current=current)

    @router.get("/api/v1/platform/operations")
    def operations(current=Depends(platform)):
        return service.operations(current=current)

    @router.post("/api/v1/platform/maintenance/resume")
    def resume(body: Resume, current=Depends(platform)):
        return service.resume(body=body, current=current)

    app.include_router(router)
