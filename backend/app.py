from .routes_auth import install_routes as install_auth_routes
from .routes_inventory import install_routes as install_inventory_routes
from .routes_experiments import install_routes as install_experiments_routes
from .routes_history import install_routes as install_history_routes
from .routes_web import install_routes as install_web_routes
from functools import partial
from .validation import validate_configuration
from .policies import active_profile
from .config import load_config
from contextlib import asynccontextmanager
import hashlib
import json
import os
from pathlib import Path
import threading
import time

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from .store import Store
from .lab import install_lab_routes
from .live import LiveStreams
from .templates import install_template_routes
from .notifications import install_notification_routes
from .throttle import Throttle


def create_app(path, passwords, runtime, dispatch=True, web_directory=None, downloads_directory=None, writer_lock=None):
    store = Store(path, passwords, runtime)
    from .study_registry import Registry

    registry = Registry(store)
    stop = threading.Event()

    @asynccontextmanager
    async def lifespan(_):
        thread = threading.Thread(target=store.dispatch, args=(stop,), daemon=True)
        dispatcher_started = False
        metadata_thread = None
        try:
            if dispatch:
                thread.start()
                dispatcher_started = True
            if getattr(runtime, "storage_backend", None) is not None:
                from .metadata_backup import backup_loop

                metadata_thread = threading.Thread(
                    target=backup_loop, args=(store, app.state.storage, stop), daemon=True
                )
                metadata_thread.start()
            yield
        finally:
            stop.set()
            # A second writer cannot take over while an old background writer
            # still owns work. Join off-loop and release only after both stop.
            if metadata_thread and metadata_thread.ident is not None:
                await run_in_threadpool(metadata_thread.join)
            if dispatcher_started:
                await run_in_threadpool(thread.join)
            if writer_lock is not None:
                writer_lock.close()

    # The interactive documentation lists every route: keep it for development, not for a served lab.
    private_docs = {} if web_directory is None else {"docs_url": None, "redoc_url": None, "openapi_url": None}
    app = FastAPI(title="HeteroES product API", lifespan=lifespan, **private_docs)
    app.state.login_failures = Throttle(5, 600)  # per caller address and username
    app.state.login_failures_by_address = Throttle(30, 600)  # per caller address, any username
    app.state.registrations = Throttle(10, 3600)
    app.state.store = store
    app.state.live = LiveStreams()

    @app.exception_handler(HTTPException)
    async def handle_http(_request, error):
        return JSONResponse({"message": str(error.detail)}, status_code=error.status_code, headers=error.headers)

    def user(authorization: str = Header(default="")):
        if not authorization.startswith("Bearer "):
            raise HTTPException(401, "Sign in to continue")
        digest = hashlib.sha256(authorization[7:].encode()).hexdigest()
        with store.db() as db:
            row = db.execute(
                "SELECT users.profile FROM sessions JOIN users ON users.id=sessions.user_id WHERE digest=? AND expires>?",
                (digest, time.time()),
            ).fetchone()
        if not row:
            raise HTTPException(401, "Session expired or revoked")
        return json.loads(row[0])

    def scoped(current=Depends(user), x_workspace_id: str = Header(default="")):
        profile = active_profile(store, current, "Your account must be active to access lab resources")
        membership = next((w for w in store.workspaces(current["userId"]) if w["workspaceId"] == x_workspace_id), None)
        if not membership:
            raise HTTPException(403, "Select a workspace you belong to")
        return {**profile, "workspaceId": x_workspace_id, "workspaceRole": membership["role"]}

    def session(current):
        return {
            "user": current,
            "workspaces": store.workspaces(current["userId"]) if current["accountStatus"] == "ACTIVE" else [],
        }

    def visible(current):
        return [
            body
            for body in store.list()
            if not body.get("archivedAt")
            and body["workspaceId"] == current["workspaceId"]
            and (current["workspaceRole"] == "ADMIN" or body["ownerUserId"] == current["userId"])
        ]

    def authorized(run_id, current):
        body = store.get(run_id)
        current = scoped(current, current["workspaceId"])
        if (
            not body
            or body.get("archivedAt")
            or body["workspaceId"] != current["workspaceId"]
            or (current["workspaceRole"] != "ADMIN" and body["ownerUserId"] != current["userId"])
        ):
            raise HTTPException(404, "Experiment not found")
        return body

    def capabilities():
        try:
            value = runtime.capabilities()
            store.ensure_workers(value["workerIds"])
            return value
        except Exception:
            raise HTTPException(503, "Runtime control service unavailable") from None

    validate = partial(
        validate_configuration,
        store=store,
        runtime=runtime,
        registry=registry,
        scoped=scoped,
        capabilities=capabilities,
    )

    install_auth_routes(app, store, user, session)
    install_inventory_routes(app, store, runtime, scoped, visible, capabilities, registry)
    install_experiments_routes(app, store, runtime, scoped, visible, authorized, validate)
    install_history_routes(app, store, runtime, scoped, visible, authorized)

    install_lab_routes(app, store, user, scoped, runtime)
    install_template_routes(app, store, scoped)
    install_notification_routes(app, store, user)
    from .devices import install_device_routes

    device_auth = install_device_routes(app, store, user, runtime)
    from .study_registry import install_routes as study_routes

    study_routes(app, registry, runtime, scoped, device_auth)
    if runtime.storage_backend is not None:
        from .recovery_storage import RecoveryStorage, install_storage_routes

        storage = RecoveryStorage(
            store, runtime.storage_backend, quota_bytes=getattr(runtime.storage_backend, "quota_bytes", 8_000_000_000)
        )
        app.state.storage = storage
        runtime.storage = storage
        install_storage_routes(app, store, storage, device_auth, user, scoped, authorized)
        if hasattr(runtime.storage_backend, "install_routes"):
            runtime.storage_backend.install_routes(app)

    install_web_routes(app, web_directory, downloads_directory)
    return app


def app_from_environment():
    private_root = os.environ.get("HETEROES_PRIVATE_CONFIG")
    if not private_root:
        raise ValueError("Set HETEROES_PRIVATE_CONFIG to the lab configuration directory")
    root = Path(private_root)
    credentials = json.loads((root / "credentials.json").read_text())
    config = load_config(root)
    from .writer_lock import acquire_writer

    writer = acquire_writer(Path(config["productStateDirectory"]) / "product.sqlite")
    try:
        return _app_from_config(root, credentials, config, writer)
    except BaseException:
        writer.close()
        raise


def _app_from_config(root, credentials, config, writer):
    if config.get("deploymentMode") != "agent":
        raise ValueError("Only agent deployment mode is supported")
    if config.get("storageMode") not in (None, "local") or config.get("storageFile"):
        raise ValueError("Only local recovery storage is supported")
    from .devices import AgentRuntime

    storage_backend = None
    if config.get("storageMode") == "local":
        from .local_storage import LocalBackend

        storage_backend = LocalBackend(
            config["storageDirectory"],
            root / "storage-signing.key",
            config.get("bulkApiUrl", config["apiUrl"]),
            config.get("storageVolumeUUID"),
            config.get("metadataStorageDirectory"),
        )
        storage_backend.quota_bytes = config.get("storageQuotaBytes", 200_000_000_000)
    runtime = AgentRuntime(storage_backend)
    runtime.server_instance_id = config.get("serverInstanceId")
    return create_app(
        Path(config["productStateDirectory"]) / "product.sqlite",
        credentials["users"],
        runtime,
        web_directory=os.environ.get("HETEROES_WEB_DIRECTORY"),
        downloads_directory=os.environ.get("HETEROES_DOWNLOADS_DIRECTORY"),
        writer_lock=writer,
    )
