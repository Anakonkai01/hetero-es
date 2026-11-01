"""Signed filesystem HTTP transfers; blocking disk work stays off the event loop."""

from anyio import CancelScope
from fastapi import HTTPException, Request
from fastapi.responses import FileResponse
from starlette.concurrency import run_in_threadpool
from ..core.errors import ServiceError
from ..storage import local_backend as local


def install_routes(app, backend):

    @app.put("/api/v1/local-storage/{token}")
    async def upload(token: str, request: Request):
        return await receive(token, request, "PUT")

    @app.put("/api/v1/public-upload/{token}")
    async def public_upload(token: str, request: Request):
        return await receive(token, request, "PUT-PUBLIC")

    async def receive(token, request, method):
        session = local._Upload()
        try:
            try:
                await run_in_threadpool(
                    backend._open_upload, session, token, request.headers.get("content-length"), method
                )
                async for chunk in request.stream():
                    await run_in_threadpool(session.write, chunk)
                return await run_in_threadpool(session.finish)
            finally:
                with CancelScope(shield=True):
                    await run_in_threadpool(session.close)
        except ServiceError as error:
            raise HTTPException(error.status_code, error.detail, headers=error.headers) from None

    @app.get("/api/v1/public-study/{token}")
    def public_study(token: str):
        try:
            grant = backend.grant(token, "GET-PUBLIC")
            path = backend.path(grant["key"])
            if not path.is_file() or path.stat().st_size > local.PUBLIC_STUDY_MAX_BYTES:
                raise HTTPException(404, "Object unavailable")
            return FileResponse(path, media_type="application/octet-stream")
        except ServiceError as error:
            raise HTTPException(error.status_code, error.detail, headers=error.headers) from None

    @app.get("/api/v1/local-storage/{token}")
    def download(token: str):
        try:
            grant = backend.grant(token, "GET")
            path = backend.path(grant["key"])
            if not path.is_file():
                raise HTTPException(404, "Object unavailable")
            return FileResponse(path, media_type="application/octet-stream")
        except ServiceError as error:
            raise HTTPException(error.status_code, error.detail, headers=error.headers) from None
