"""Account/profile HTTP adapters; persistence and policy live in services/."""

from fastapi import APIRouter, Depends, Header, Request, Response

from ..request_models import Registration, ProfileEdit, PasswordEdit
from ..throttle import client_address
from ..core.errors import ServiceError


def install_routes(app, store, user):
    router = APIRouter()
    accounts = store.accounts

    if app.state.auth_mode == "oidc":

        @router.post("/api/v1/auth/register")
        @router.post("/api/v1/auth/password")
        @router.post("/api/v1/auth/revoke-other-sessions")
        def external_accounts():
            raise ServiceError(404, "Use HeteroES ID to manage sign-in and account security")

        @router.patch("/api/v1/profile")
        def edit_external_profile(body: ProfileEdit, current=Depends(user)):
            return accounts.edit_profile(current["userId"], body.model_dump(exclude_none=True))

        app.include_router(router)
        return

    @router.post("/api/v1/auth/register", status_code=201)
    def register(body: Registration, request: Request):
        address = client_address(request.client.host if request.client else None, request.headers)
        return accounts.register(body.username, body.password, body.displayName, address, app.state.registrations)

    @router.patch("/api/v1/profile")
    def edit_profile(body: ProfileEdit, current=Depends(user)):
        return accounts.edit_profile(current["userId"], body.model_dump(exclude_none=True))

    @router.post("/api/v1/auth/password", status_code=204)
    def change_password(body: PasswordEdit, current=Depends(user), authorization: str = Header()):
        accounts.change_password(current["userId"], body.currentPassword, body.newPassword, authorization[7:])
        return Response(status_code=204)

    @router.post("/api/v1/auth/revoke-other-sessions", status_code=204)
    def revoke_other_sessions(current=Depends(user), authorization: str = Header()):
        accounts.revoke_other_sessions(current["userId"], authorization[7:])
        return Response(status_code=204)

    app.include_router(router)
