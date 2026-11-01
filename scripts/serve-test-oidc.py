#!/usr/bin/env python3
"""Own an ephemeral loopback OIDC protocol fixture and product app. Not a Keycloak/deployment acceptance server."""

import base64
import hashlib
import html
import json
from pathlib import Path
import secrets
import socket
import sys
from tempfile import TemporaryDirectory
import time
from urllib.parse import parse_qs, urlencode

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "runtime/src"))

import jwt  # noqa: E402 — fixture imports after its explicit source path
from cryptography.hazmat.primitives.asymmetric import rsa  # noqa: E402 — fixture imports after its explicit source path
from fastapi import HTTPException, Request  # noqa: E402 — fixture imports after its explicit source path
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse  # noqa: E402 — fixture imports after its explicit source path
from fastapi.staticfiles import StaticFiles  # noqa: E402 — fixture imports after its explicit source path
import uvicorn  # noqa: E402 — fixture imports after its explicit source path

from backend.apps.factory import create_app  # noqa: E402 — fixture imports after its explicit source path
from backend.services.devices import AgentRuntime  # noqa: E402 — fixture imports after its explicit source path


def main():
    with TemporaryDirectory(prefix="heteroes-oidc-fixture-") as temporary, socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        origin = "http://127.0.0.1:" + str(listener.getsockname()[1])
        issuer = origin + "/fixture-id"
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        codes, refreshes = {}, {}
        receipt = {"pkceVerified": False, "codeGrants": 0, "refreshGrants": 0, "logouts": 0}
        app = create_app(
            Path(temporary) / "product.sqlite",
            {},
            AgentRuntime(),
            dispatch=False,
            auth_mode="oidc",
            oidc_issuer=issuer,
            oidc_jwks_url=issuer + "/jwks",
        )

        @app.get("/config.json")
        def config():
            return {"authMode": "oidc", "basePath": "/lab/", "issuer": issuer, "clientId": "heteroes-web"}

        @app.get("/fixture-receipt")
        def counts():
            return receipt

        @app.get("/fixture-id/.well-known/openid-configuration")
        def discovery():
            return {
                "issuer": issuer,
                "authorization_endpoint": issuer + "/authorize",
                "token_endpoint": issuer + "/token",
                "jwks_uri": issuer + "/jwks",
                "end_session_endpoint": issuer + "/logout",
                "response_types_supported": ["code"],
                "subject_types_supported": ["public"],
                "id_token_signing_alg_values_supported": ["RS256"],
                "code_challenge_methods_supported": ["S256"],
                "token_endpoint_auth_methods_supported": ["none"],
            }

        @app.get("/fixture-id/jwks")
        def jwks():
            return {
                "keys": [
                    {
                        **json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key())),
                        "kid": "browser-fixture",
                        "alg": "RS256",
                        "use": "sig",
                    }
                ]
            }

        def authorize(request, approved):
            query = dict(request.query_params)
            redirect = query.get("redirect_uri")
            if (
                redirect not in {origin + "/lab/oidc/callback", origin + "/lab/oidc/silent"}
                or query.get("client_id") != "heteroes-web"
            ):
                raise HTTPException(400, "Invalid fixture client")
            if query.get("code_challenge_method") != "S256" or not query.get("code_challenge"):
                raise HTTPException(400, "PKCE is required")
            if query.get("prompt") == "none" and request.cookies.get("fixture-sso") != "signed-in":
                return RedirectResponse(
                    redirect + "?" + urlencode({"error": "login_required", "state": query.get("state", "")}),
                    status_code=303,
                )
            if not approved and request.cookies.get("fixture-sso") != "signed-in":
                return HTMLResponse(
                    '<form method="post" action="'
                    + html.escape(str(request.url), quote=True)
                    + '"><button>Approve fixture identity</button></form>'
                )
            code = secrets.token_urlsafe(32)
            codes[code] = query
            response = RedirectResponse(
                redirect + "?" + urlencode({"code": code, "state": query.get("state", "")}), status_code=303
            )
            response.set_cookie("fixture-sso", "signed-in", httponly=True, samesite="lax")
            return response

        @app.get("/fixture-id/authorize")
        def begin(request: Request):
            return authorize(request, False)

        @app.post("/fixture-id/authorize")
        def confirm(request: Request):
            return authorize(request, True)

        @app.post("/fixture-id/token")
        async def token(request: Request):
            values = parse_qs((await request.body()).decode())
            data = {name: value[0] for name, value in values.items()}
            if data.get("client_id") != "heteroes-web":
                raise HTTPException(400, "Invalid fixture client")
            if data.get("grant_type") == "authorization_code":
                query = codes.pop(data.get("code"), None)
                challenge = (
                    base64.urlsafe_b64encode(hashlib.sha256(data.get("code_verifier", "").encode()).digest())
                    .rstrip(b"=")
                    .decode()
                )
                if (
                    not query
                    or query.get("code_challenge") != challenge
                    or query["redirect_uri"] != data.get("redirect_uri")
                ):
                    raise HTTPException(400, "Invalid code or PKCE verifier")
                receipt["pkceVerified"] = True
                receipt["codeGrants"] += 1
            elif data.get("grant_type") == "refresh_token":
                query = refreshes.pop(data.get("refresh_token"), None)
                if not query:
                    raise HTTPException(400, "Invalid refresh grant")
                receipt["refreshGrants"] += 1
            else:
                raise HTTPException(400, "Invalid grant")
            now = int(time.time())
            claims = {
                "iss": issuer,
                "aud": "heteroes-web",
                "azp": "heteroes-web",
                "sub": "fixture-subject",
                "preferred_username": "browser-fixture",
                "realm_access": {"roles": ["lab-admin"]},
                "exp": now + 75,
                "iat": now,
                "auth_time": now,
                "nonce": query.get("nonce"),
            }
            encoded = jwt.encode(claims, key, algorithm="RS256", headers={"kid": "browser-fixture"})
            refresh = secrets.token_urlsafe(32)
            refreshes[refresh] = query
            return JSONResponse(
                {
                    "access_token": encoded,
                    "id_token": encoded,
                    "refresh_token": refresh,
                    "expires_in": 75,
                    "token_type": "Bearer",
                    "scope": "openid profile email",
                },
                headers={"Cache-Control": "no-store"},
            )

        @app.get("/fixture-id/logout")
        def logout(request: Request):
            query = request.query_params
            if query.get("post_logout_redirect_uri") != origin + "/lab/oidc/logout":
                raise HTTPException(400, "Invalid logout redirect")
            receipt["logouts"] += 1
            response = RedirectResponse(
                origin + "/lab/oidc/logout?" + urlencode({"state": query.get("state", "")}), status_code=303
            )
            response.delete_cookie("fixture-sso")
            return response

        web = ROOT / "frontend/dist"
        app.mount("/assets", StaticFiles(directory=web / "assets"))
        app.mount("/lab/assets", StaticFiles(directory=web / "assets"))

        @app.get("/lab/{path:path}")
        def page(path: str):
            candidate = (web / path).resolve()
            if candidate.is_relative_to(web.resolve()) and candidate.is_file():
                return FileResponse(candidate)
            return FileResponse(web / "index.html")

        print(json.dumps({"origin": origin, "scope": "ephemeral OIDC browser fixture"}), flush=True)
        server = uvicorn.Server(uvicorn.Config(app, log_level="warning", access_log=False))
        server.run(sockets=[listener])


if __name__ == "__main__":
    main()
