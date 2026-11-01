"""Templates HTTP adapters."""

from fastapi import Depends, HTTPException, Response
from fastapi import APIRouter
from ..services.templates import operations, clean_config as _clean_config
from ..core.errors import ServiceError


def install_routes(app, store, scoped):
    service = operations(store, scoped)
    router = APIRouter()

    @app.get("/api/v1/experiment-templates")
    def list_templates(current=Depends(scoped)):
        return service.list_templates(current=current)

    @app.post("/api/v1/experiment-templates", status_code=201)
    def create_template(body: dict, current=Depends(scoped)):
        return service.create_template(body=body, current=current)

    @app.delete("/api/v1/experiment-templates/{template_id}", status_code=204)
    def delete_template(template_id: str, current=Depends(scoped)):
        service.delete_template(template_id=template_id, current=current)
        return Response(status_code=204)

    app.include_router(router)


def clean_config(config):
    """Compatibility HTTP boundary for existing in-process template callers."""
    try:
        return _clean_config(config)
    except ServiceError as error:
        raise HTTPException(error.status_code, error.detail, headers=error.headers) from None
