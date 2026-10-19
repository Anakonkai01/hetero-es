"""Retired mock/cloud routes cannot remain as active API operations."""

import pytest


@pytest.mark.parametrize(
    "method,path",
    [
        ("GET", "/api/v1/workspaces"),
        ("GET", "/api/v1/worker-registry"),
        ("GET", "/api/v1/my-workers"),
        ("GET", "/api/v1/my-resource-submissions"),
        ("GET", "/api/v1/experiments/unknown/monitoring-events"),
        ("PATCH", "/api/v1/device/endpoints"),
        ("POST", "/api/v1/no-such-operation"),
    ],
)
def test_retired_operations_are_absent(lab, method, path):
    client, _, _, auth = lab
    assert client.request(method, path, headers=auth, json={}).status_code in (404, 405)
