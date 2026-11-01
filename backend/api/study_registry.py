"""Study_Registry HTTP adapters."""

from ..core.study_models import ImportData, DatasetUpload, DatasetBuild, DatasetLimits, RegisterModel
from fastapi import Depends
from fastapi import APIRouter
from ..services.study_registry import operations


def install_routes(app, registry, runtime, scoped, device_auth):
    service = operations(registry, runtime, scoped, device_auth)
    router = APIRouter()

    @app.post("/api/v1/datasets/import", status_code=201)
    def import_data(body: ImportData, current=Depends(scoped)):
        return service.import_data(body=body, current=current)

    @app.get("/api/v1/platform/dataset-limits")
    def get_dataset_limits(current=Depends(scoped)):
        return service.get_dataset_limits(current=current)

    @app.put("/api/v1/platform/dataset-limits")
    def set_dataset_limits(body: DatasetLimits, current=Depends(scoped)):
        return service.set_dataset_limits(body=body, current=current)

    @app.post("/api/v1/datasets/upload-plan", status_code=201)
    def dataset_upload_plan(body: DatasetUpload, current=Depends(scoped)):
        return service.dataset_upload_plan(body=body, current=current)

    @app.post("/api/v1/datasets/uploads/{upload_id}/build", status_code=201)
    def build_uploaded_dataset(upload_id: str, body: DatasetBuild, current=Depends(scoped)):
        return service.build_uploaded_dataset(upload_id=upload_id, body=body, current=current)

    @app.post("/api/v1/models/register", status_code=201)
    def register_model(body: RegisterModel, current=Depends(scoped)):
        return service.register_model(body=body, current=current)

    @app.post("/api/v1/models/{asset_id}/upload-plan")
    def upload_plan(asset_id: str, sizes: dict, current=Depends(scoped)):
        return service.upload_plan(asset_id=asset_id, sizes=sizes, current=current)

    @app.post("/api/v1/models/{asset_id}/publish")
    def publish(asset_id: str, current=Depends(scoped)):
        return service.publish(asset_id=asset_id, current=current)

    @app.post("/api/v1/device/study-transfer")
    def transfer(body: dict, current=Depends(device_auth)):
        return service.transfer(body=body, current=current)

    app.include_router(router)
