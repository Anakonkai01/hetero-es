"""Inventory HTTP adapters."""

from fastapi import Depends
from fastapi import APIRouter
from ..services.inventory import operations as business_operations


def install_routes(app, store, runtime, scoped, visible, capabilities, registry):
    service = business_operations(store, runtime, scoped, visible, capabilities, registry)
    router = APIRouter()

    @router.get("/api/v1/health")
    def health():
        return service.health()

    @router.get("/api/v1/capabilities")
    def get_capabilities(current=Depends(scoped)):
        return service.get_capabilities(current=current)

    @router.get("/api/v1/resources")
    def resources(current=Depends(scoped)):
        return service.resources(current=current)

    @router.get("/api/v1/models")
    def models(current=Depends(scoped)):
        return service.models(current=current)

    @router.get("/api/v1/workers")
    def workers(current=Depends(scoped)):
        return service.workers(current=current)

    @router.get("/api/v1/workers/{worker_id}")
    def worker(worker_id: str, current=Depends(scoped)):
        return service.worker(worker_id=worker_id, current=current)

    @router.get("/api/v1/datasets")
    def datasets(current=Depends(scoped)):
        return service.datasets(current=current)

    app.include_router(router)
