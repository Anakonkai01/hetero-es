"""Product route ownership and registration, independent of FastAPI's lazy router representation."""

from copy import copy

SERVICES = frozenset({"all", "api", "devices", "storage", "scheduler"})
OPERATIONAL = frozenset({"/healthz", "/readyz", "/metrics"})
_FRAMEWORK = frozenset({"/openapi.json", "/docs", "/docs/oauth2-redirect", "/redoc"})
_HTTP_METHODS = frozenset({"get", "post", "put", "patch", "delete", "head", "options", "trace"})

_DEVICES = frozenset(
    {
        ("DELETE", "/api/v1/device"),
        ("DELETE", "/api/v1/devices/{device_id}"),
        ("DELETE", "/api/v1/platform/devices/{device_id}"),
        ("GET", "/api/v1/device/summary"),
        ("GET", "/api/v1/devices"),
        ("GET", "/api/v1/platform/devices"),
        ("PATCH", "/api/v1/device/name"),
        ("PATCH", "/api/v1/device/qualification"),
        ("PATCH", "/api/v1/devices/{device_id}"),
        ("PATCH", "/api/v1/devices/{device_id}/configuration"),
        ("PATCH", "/api/v1/devices/{device_id}/contribution"),
        ("PATCH", "/api/v1/devices/{device_id}/endpoints"),
        ("PATCH", "/api/v1/platform/devices/{device_id}"),
        ("POST", "/api/v1/device/contribution"),
        ("POST", "/api/v1/device/enroll"),
        ("POST", "/api/v1/device/model-transfer"),
        ("POST", "/api/v1/device/poll"),
        ("POST", "/api/v1/device/study-transfer"),
        ("POST", "/api/v1/device/worker-command"),
        ("POST", "/api/v1/devices/pairing-codes"),
        ("POST", "/api/v1/devices/{device_id}/contribution"),
    }
)

_STORAGE = frozenset(
    {
        ("DELETE", "/api/v1/device/recovery-points/{point_id}"),
        ("DELETE", "/api/v1/recovery-points/{point_id}"),
        ("GET", "/api/v1/artifacts"),
        ("GET", "/api/v1/artifacts/{artifact_id}/download"),
        ("GET", "/api/v1/cloud-downloads/{ticket_digest}"),
        ("GET", "/api/v1/device/recovery-points/{point_id}"),
        ("GET", "/api/v1/experiments/{run_id}/recovery-points"),
        ("GET", "/api/v1/local-storage/{token}"),
        ("GET", "/api/v1/public-study/{token}"),
        ("POST", "/api/v1/artifacts/{artifact_id}/download-ticket"),
        ("POST", "/api/v1/datasets/upload-plan"),
        ("POST", "/api/v1/datasets/uploads/{upload_id}/build"),
        ("POST", "/api/v1/device/recovery-points"),
        ("POST", "/api/v1/device/recovery-points/complete-object"),
        ("POST", "/api/v1/device/recovery-points/{point_id}/verify"),
        ("POST", "/api/v1/experiments/{run_id}/recovery-import"),
        ("POST", "/api/v1/experiments/{run_id}/recovery-import/complete-object"),
        ("POST", "/api/v1/experiments/{run_id}/recovery-import/{point_id}/verify"),
        ("POST", "/api/v1/models/{asset_id}/publish"),
        ("POST", "/api/v1/models/{asset_id}/upload-plan"),
        ("POST", "/api/v1/recovery-points/{point_id}/download-plan"),
        ("PUT", "/api/v1/local-storage/{token}"),
        ("PUT", "/api/v1/public-upload/{token}"),
    }
)


def owner(method, path):
    pair = (method.upper(), path)
    if pair in _DEVICES:
        return "devices"
    if pair in _STORAGE:
        return "storage"
    return "api"


class ServiceRegistration:
    """Keep dependency factories available, but register only HTTP handlers owned by this process."""

    def __init__(self, app, service):
        if service not in SERVICES:
            raise ValueError("Unknown backend service")
        self.app, self.service = app, service

    def accepts(self, method, path):
        return self.service == "all" or owner(method, path) == self.service

    def __getattr__(self, name):
        if name in _HTTP_METHODS:

            def register(path, *arguments, **options):
                if self.accepts(name, path):
                    return getattr(self.app, name)(path, *arguments, **options)
                return lambda endpoint: endpoint

            return register
        return getattr(self.app, name)

    def include_router(self, router, **options):
        prefix = options.get("prefix", "")
        filtered = copy(router)
        filtered.routes = []
        for route in router.routes:
            if hasattr(route, "original_router"):
                raise ValueError("Register nested service routers explicitly")
            methods = getattr(route, "methods", ())
            accepted = [self.accepts(method, prefix + route.path) for method in methods]
            if accepted and any(accepted) != all(accepted):
                raise ValueError("A route mixes methods belonging to different services")
            if accepted and all(accepted):
                filtered.routes.append(route)
        if filtered.routes:
            return self.app.include_router(filtered, **options)

    def mount(self, path, application, **options):
        if self.service in {"all", "api"}:
            return self.app.mount(path, application, **options)


def inventory(app):
    """Export actual registered routes, walking lazy FastAPI router inclusions instead of guessing from prefixes."""
    product, operational, mounts = [], [], []

    def walk(router, prefix=""):
        for route in router.routes:
            if hasattr(route, "original_router"):
                walk(route.original_router, prefix + getattr(route, "prefix", ""))
                continue
            path = prefix + route.path
            if path in _FRAMEWORK:
                continue
            if type(route).__name__ == "Mount":
                mounts.append({"path": path, "owner": "api"})
                continue
            for method in sorted(route.methods):
                if path in OPERATIONAL:
                    operational.append({"method": method, "path": path})
                else:
                    product.append({"method": method, "path": path, "owner": owner(method, path)})

    walk(app.router)
    key = lambda row: (row.get("path", ""), row.get("method", ""))
    return {
        "service": app.state.service,
        "product": sorted(product, key=key),
        "operational": sorted(operational, key=key),
        "mounts": sorted(mounts, key=key),
    }
