"""Local authentication HTTP adapter."""

from fastapi import APIRouter, Depends, Header, Request, Response

from ..request_models import Login
from ..throttle import client_address


def install_routes(app, store, user, session):
    router = APIRouter()
    accounts = store.accounts

    @router.post("/api/v1/auth/login")
    def sign_in(body: Login, request: Request):
        address = client_address(request.client.host if request.client else None, request.headers)
        return accounts.sign_in(
            body.username,
            body.password,
            address,
            app.state.login_failures,
            app.state.login_failures_by_address,
            session,
        )

    @router.get("/api/v1/auth/session")
    def get_session(current=Depends(user)):
        return session(current)

    @router.post("/api/v1/auth/logout", status_code=204)
    def sign_out(current=Depends(user), authorization: str = Header()):
        accounts.sign_out(authorization[7:])
        return Response(status_code=204)

    app.include_router(router)
