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
from .routing import SERVICES, ServiceRegistration
from ..api.operational import install_routes as install_operational_routes
from ..services.scheduler_controller import SchedulerController


def create_app(
    path,
    passwords,
    runtime,
    dispatch=True,
    web_directory=None,
    downloads_directory=None,
    writer_lock=None,
    *,
    service="all",
    database_url=None,
    database_connect_args=None,
    auth_mode="local",
    oidc_issuer=None,
    oidc_jwks_url=None,
):
    if service not in SERVICES:
        raise ValueError("Unknown backend service")
    if auth_mode not in {"local", "oidc"}:
        raise ValueError("Unknown authentication mode")
    verifier = None
    if auth_mode == "oidc":
        from ..services.oidc import OIDCAccounts, OIDCVerifier

        verifier = OIDCVerifier(oidc_issuer, oidc_jwks_url)
    store = Store(
        path,
        passwords if auth_mode == "local" else {},
        runtime,
        database_url=database_url,
        database_connect_args=database_connect_args,
    )
    store.authentication = OIDCAccounts(store, verifier) if verifier else store.accounts
    from ..services.study_registry import Registry

    registry = Registry(store)
    stop = threading.Event()
    scheduler = SchedulerController(store)

    @asynccontextmanager
    async def lifespan(_):
        thread = threading.Thread(target=scheduler.run, args=(stop,), daemon=True)
        dispatcher_started = False
        metadata_thread = None
        try:
            if dispatch and service in {"all", "scheduler"}:
                thread.start()
                dispatcher_started = True
            if service in {"all", "storage"} and getattr(runtime, "storage_backend", None) is not None:
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
            store.close()
            if writer_lock is not None:
                writer_lock.close()

    # The interactive documentation lists every route: keep it for development, not for a served lab.
    private_docs = (
        {} if web_directory is None and service == "all" else {"docs_url": None, "redoc_url": None, "openapi_url": None}
    )
    app = FastAPI(title="HeteroES product API", lifespan=lifespan, **private_docs)
    app.state.login_failures = Throttle(5, 600)  # per caller address and username
    app.state.login_failures_by_address = Throttle(30, 600)  # per caller address, any username
    app.state.registrations = Throttle(10, 3600)
    app.state.store = store
    app.state.service = service
    app.state.auth_mode = auth_mode
    app.state.scheduler = scheduler
    app.state.live = LiveStreams()

    @app.exception_handler(ServiceError)
    @app.exception_handler(HTTPException)
    async def handle_http(_request, error):
        return JSONResponse({"message": str(error.detail)}, status_code=error.status_code, headers=error.headers)

    user = local_user(store.authentication)
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

    install_operational_routes(app, store, service)
    registration = ServiceRegistration(app, service)

    install_auth_routes(registration, store, user, session)
    install_inventory_routes(registration, store, runtime, scoped, visible, capabilities, registry)
    install_experiments_routes(
        registration, store, runtime, scoped, visible, authorized, validate, service_scoped=access.scope
    )
    install_history_routes(registration, store, runtime, scoped, visible, authorized)

    install_lab_routes(registration, store, user, scoped, runtime)
    install_template_routes(registration, store, scoped)
    install_notification_routes(registration, store, user)
    from ..api.devices import install_routes as install_device_routes

    device_auth = install_device_routes(registration, store, user, runtime)
    from ..api.study_registry import install_routes as study_routes

    study_routes(registration, registry, runtime, scoped, device_auth)
    from ..api.model_qualification import install_routes as qualification_routes

    qualification_routes(registration, registry, runtime, scoped, device_auth)
    if runtime.storage_backend is not None:
        from ..services.recovery_storage import RecoveryStorage
        from ..api.recovery_storage import install_routes as install_storage_routes

        storage = RecoveryStorage(
            store, runtime.storage_backend, quota_bytes=getattr(runtime.storage_backend, "quota_bytes", 8_000_000_000)
        )
        app.state.storage = storage
        runtime.storage = storage
        install_storage_routes(registration, store, storage, device_auth, user, scoped, authorized)
        if hasattr(runtime.storage_backend, "install_routes"):
            runtime.storage_backend.install_routes(registration)

    install_web_routes(registration, web_directory, downloads_directory)
    return app


def app_from_environment(*, service=None):
    service = service or os.environ.get("HETEROES_SERVICE", "all")
    if service not in SERVICES:
        raise ValueError("Unknown backend service")
    private_root = os.environ.get("HETEROES_PRIVATE_CONFIG")
    if not private_root:
        raise ValueError("Set HETEROES_PRIVATE_CONFIG to the lab configuration directory")
    root = Path(private_root)
    credentials = json.loads((root / "credentials.json").read_text())
    config = load_config(root)
    database_url = os.environ.get("HETEROES_DATABASE_URL") or config.get("databaseUrl")
    postgres = False
    path = Path(config["productStateDirectory"]) / "product.sqlite"
    if database_url:
        from sqlalchemy.engine import make_url
        from sqlalchemy.exc import ArgumentError

        try:
            url = make_url(database_url)
        except ArgumentError:
            raise ValueError("Invalid database URL") from None
        postgres = url.get_backend_name() in {"postgres", "postgresql"}
        if not postgres:
            if url.get_backend_name() != "sqlite" or not url.database or url.database == ":memory:":
                raise ValueError("Use a persistent SQLite file or PostgreSQL database")
            path = Path(url.database).resolve()
    if service != "all" and not postgres:
        raise ValueError("Split production services require PostgreSQL")
    writer = None
    if not postgres:
        from ..core.writer_lock import acquire_writer

        writer = acquire_writer(path)
    try:
        return _app_from_config(root, credentials, config, writer, service=service, database_url=database_url)
    except BaseException:
        if writer is not None:
            writer.close()
        raise


def _app_from_config(root, credentials, config, writer, *, service="all", database_url=None):
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
        service=service,
        database_url=database_url,
        auth_mode=os.environ.get("HETEROES_AUTH_MODE", config.get("authMode", "local")),
        oidc_issuer=os.environ.get("HETEROES_OIDC_ISSUER", config.get("oidcIssuer")),
        oidc_jwks_url=os.environ.get("HETEROES_OIDC_JWKS_URL", config.get("oidcJwksUrl")),
    )
