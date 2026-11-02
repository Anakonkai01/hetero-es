"""Shared process diagnostics, registered before the SPA catch-all; metrics expand in B7."""

from fastapi.responses import JSONResponse, Response


def install_routes(app, store, service):
    @app.get("/healthz", include_in_schema=False)
    def health():
        return {"ok": True, "service": service}

    @app.get("/readyz", include_in_schema=False)
    def ready():
        try:
            store.database.ping()
            backend = getattr(store.runtime, "storage_backend", None)
            if backend is not None:
                if hasattr(backend, "ready"):
                    backend.ready()
                else:
                    backend.inventory()
        except Exception as error:
            return JSONResponse(
                {"ready": False, "service": service, "errorType": type(error).__name__}, status_code=503
            )
        return {"ready": True, "service": service}

    @app.get("/metrics", include_in_schema=False)
    def metrics():
        body, content_type = app.state.metrics.render()
        return Response(body, headers={"Content-Type": content_type})
