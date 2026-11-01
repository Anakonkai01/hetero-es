from ..api.auth import install_routes as install_auth_routes
from ..api.inventory import install_routes as install_inventory_routes
from ..api.experiments import install_routes as install_experiments_routes
from ..api.history import install_routes as install_history_routes
from ..api.web import install_routes as install_web_routes
from functools import partial
from ..services.validation import validate_configuration
from ..core.config import load_config
from contextlib import asynccontextmanager
import json
import os
from pathlib import Path
import threading

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from ..services.store import Store
from ..api.lab import install_lab_routes
from ..api.live import LiveStreams
from ..api.templates import install_routes as install_template_routes
from ..api.notifications import install_routes as install_notification_routes
from ..throttle import Throttle
from ..api.security import local_user, workspace_scope
from ..services.access import AccessService
from ..core.errors import ServiceError


def create_app(path, passwords, runtime, dispatch=True, web_directory=None, downloads_directory=None, writer_lock=None):
    store = Store(path, passwords, runtime)
    from ..services.study_registry import Registry

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
                from ..services.metadata_backup import backup_loop

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

    @app.exception_handler(ServiceError)
    @app.exception_handler(HTTPException)
    async def handle_http(_request, error):
        return JSONResponse({"message": str(error.detail)}, status_code=error.status_code, headers=error.headers)

    user = local_user(store.accounts)
    access = AccessService(store, runtime)

    scoped = workspace_scope(access, user)

    session = store.accounts.session

    visible = access.visible

    authorized = access.authorized

    capabilities = access.capabilities

    validate = partial(
        validate_configuration,
        store=store,
        runtime=runtime,
        registry=registry,
        scoped=access.scope,
        capabilities=capabilities,
    )

    install_auth_routes(app, store, user, session)
    install_inventory_routes(app, store, runtime, scoped, visible, capabilities, registry)
    install_experiments_routes(app, store, runtime, scoped, visible, authorized, validate, service_scoped=access.scope)
    install_history_routes(app, store, runtime, scoped, visible, authorized)

    install_lab_routes(app, store, user, scoped, runtime)
    install_template_routes(app, store, scoped)
    install_notification_routes(app, store, user)
    from ..api.devices import install_routes as install_device_routes

    device_auth = install_device_routes(app, store, user, runtime)
    from ..api.study_registry import install_routes as study_routes

    study_routes(app, registry, runtime, scoped, device_auth)
    from ..api.model_qualification import install_routes as qualification_routes

    qualification_routes(app, registry, runtime, scoped, device_auth)
    if runtime.storage_backend is not None:
        from ..services.recovery_storage import RecoveryStorage
        from ..api.recovery_storage import install_routes as install_storage_routes

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
    from ..core.writer_lock import acquire_writer

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
    from ..services.devices import AgentRuntime

    storage_backend = None
    if config.get("storageMode") == "local":
        from ..storage.local_backend import LocalBackend

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
