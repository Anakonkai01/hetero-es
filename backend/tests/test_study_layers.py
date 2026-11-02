"""Study registry errors and scope stay independent of the HTTP layer."""

import pytest

from backend.core.errors import ServiceError
from backend.services.study_registry import Registry


def test_registry_lookup_preserves_workspace_scope_and_uses_plain_errors(lab):
    _, store, _, _ = lab
    registry = Registry(store)
    asset = {"id": "study-layer-fixture", "name": "Private study fixture"}
    registry.save(asset, "lab", "admin", "dataset")
    assert registry.get(asset["id"], "lab", "dataset") == asset
    for workspace, kind in (("another-workspace", "dataset"), ("lab", "model")):
        with pytest.raises(ServiceError) as missing:
            registry.get(asset["id"], workspace, kind)
        assert missing.value.status_code == 404
