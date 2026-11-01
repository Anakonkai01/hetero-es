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
        except Exception as error:
            return JSONResponse(
                {"ready": False, "service": service, "errorType": type(error).__name__}, status_code=503
            )
        return {"ready": True, "service": service}

    @app.get("/metrics", include_in_schema=False)
    def metrics():
        return Response(f'heteroes_service_up{{service="{service}"}} 1\n', media_type="text/plain; version=0.0.4")
