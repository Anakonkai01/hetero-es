"""Compatibility exports during backend layer extraction."""

from .api.study_registry import install_routes as install_routes
from .services.study_registry import Registry as Registry, dataset_limits as dataset_limits
from .services.study_registry import dataset as dataset
from .core.study_models import (
    ImportData as ImportData,
    DatasetUpload as DatasetUpload,
    DatasetBuild as DatasetBuild,
    DatasetLimits as DatasetLimits,
    RegisterModel as RegisterModel,
)
