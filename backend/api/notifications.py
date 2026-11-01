"""Notifications HTTP adapters."""

from fastapi import Depends
from fastapi import APIRouter
from ..services.notifications import operations


def install_routes(app, store, user):
    service = operations(store, user)
    router = APIRouter()

    @app.get("/api/v1/notifications")
    def list_notifications(limit: int = 30, current=Depends(user)):
        return service.list_notifications(limit=limit, current=current)

    @app.post("/api/v1/notifications/read")
    def read_notifications(body: dict, current=Depends(user)):
        return service.read_notifications(body=body, current=current)

    app.include_router(router)
