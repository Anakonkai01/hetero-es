"""Bounded public dataset proxy; bulk bytes use the separately signed private S3 endpoint."""

from anyio import CancelScope
from fastapi import HTTPException, Request
from fastapi.responses import StreamingResponse
from pathlib import Path
import shutil
from starlette.concurrency import run_in_threadpool
import tempfile

from ..core.errors import ServiceError
from ..storage.local_backend import _Upload


def install_routes(app, datasets):
    @app.get("/api/v1/local-storage/{token}")
    @app.put("/api/v1/local-storage/{token}")
    def private_transfer(token: str):
        raise HTTPException(403, "Private LAN/Tailscale transfer required")

    @app.put("/api/v1/public-upload/{token}")
    async def upload(token: str, request: Request):
        session = _Upload()
        work = None
        try:
            grant = await run_in_threadpool(datasets.public_upload_grant, token, request.headers.get("content-length"))
            if (await run_in_threadpool(shutil.disk_usage, datasets.root)).free < grant["size"] + 64 * 1024**2:
                raise ServiceError(507, "Upload staging is full")
            work = Path(await run_in_threadpool(tempfile.mkdtemp, prefix=".public-upload-", dir=datasets.root))
            target = work / "payload"
            await run_in_threadpool(session.open, target, grant["size"])
            async for chunk in request.stream():
                await run_in_threadpool(session.write, chunk)
            receipt = await run_in_threadpool(session.finish)
            await run_in_threadpool(datasets.put_file, grant["key"], target)
            return receipt
        except ServiceError as error:
            raise HTTPException(error.status_code, error.detail, headers=error.headers) from None
        except (OSError, ValueError):
            raise HTTPException(409, "Dataset upload could not complete") from None
        finally:
            # Wait for an owned thread before closing/removing its files, including client cancellation.
            with CancelScope(shield=True):
                await run_in_threadpool(session.close)
                if work is not None:
                    await run_in_threadpool(shutil.rmtree, work, True)

    @app.get("/api/v1/public-study/{token}")
    def download(token: str):
        try:
            chunks, size = datasets.public_download(token)
            return StreamingResponse(
                chunks, media_type="application/octet-stream", headers={"Content-Length": str(size)}
            )
        except ServiceError as error:
            raise HTTPException(error.status_code, error.detail, headers=error.headers) from None
        except ValueError:
            raise HTTPException(503, "Dataset storage unavailable") from None
