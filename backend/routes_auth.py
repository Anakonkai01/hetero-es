from .request_models import Login
import hashlib
import json
import secrets
import time

from argon2.exceptions import VerificationError
from fastapi import Depends, Header, HTTPException, Request, Response

from .throttle import client_address


from fastapi import APIRouter


def install_routes(app, store, user, session):
    router = APIRouter()

    def authenticate(body: Login):
        with store.db() as db:
            row = db.execute(
                "SELECT id,hash,profile FROM users WHERE json_extract(profile,'$.username')=?", (body.username,)
            ).fetchone()
            try:
                store.hasher.verify(row["hash"] if row else store.hasher.hash("unknown-user"), body.password)
            except VerificationError:
                raise HTTPException(401, "Invalid username or password") from None
            if not row:
                raise HTTPException(401, "Invalid username or password")
            token = secrets.token_urlsafe(32)
            db.execute(
                "INSERT INTO sessions VALUES (?,?,?)",
                (hashlib.sha256(token.encode()).hexdigest(), row["id"], time.time() + 43200),
            )
            return {**session(json.loads(row["profile"])), "accessToken": token}

    @router.post("/api/v1/auth/login")
    def sign_in(body: Login, request: Request):
        address = client_address(request.client.host if request.client else None, request.headers)
        user_key = (address, body.username.lower())
        state = app.state
        wait = max(state.login_failures.retry_after(user_key), state.login_failures_by_address.retry_after(address))
        if wait:
            raise HTTPException(
                429, f"Too many attempts. Try again in {wait} seconds.", headers={"Retry-After": str(wait)}
            )
        try:
            result = authenticate(body)
        except HTTPException as error:
            if error.status_code == 401:
                state.login_failures.record(user_key)
                state.login_failures_by_address.record(address)
            raise
        state.login_failures.clear(user_key)
        return result

    @router.get("/api/v1/auth/session")
    def get_session(current=Depends(user)):
        return session(current)

    @router.post("/api/v1/auth/logout", status_code=204)
    def sign_out(current=Depends(user), authorization: str = Header()):
        with store.db() as db:
            db.execute("DELETE FROM sessions WHERE digest=?", (hashlib.sha256(authorization[7:].encode()).hexdigest(),))
        return Response(status_code=204)

    app.include_router(router)
