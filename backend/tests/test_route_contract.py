"""The full pre-split product route contract survives every domain extraction."""

import json
from pathlib import Path

from backend.app import create_app
from backend.devices import AgentRuntime
from backend.local_storage import LocalBackend


def test_product_route_contract_matches_archived_pre_split_inventory(tmp_path, monkeypatch):
    monkeypatch.delenv("HETEROES_PRIVATE_CONFIG", raising=False)
    web = tmp_path / "web"
    (web / "assets").mkdir(parents=True)
    (web / "index.html").write_text("<html>Contract fixture</html>")
    downloads = tmp_path / "downloads"
    downloads.mkdir()
    storage = LocalBackend(tmp_path / "objects", tmp_path / "signing.key", "http://127.0.0.1:18052")
    app = create_app(
        tmp_path / "product.sqlite",
        {"admin": "route-contract-test-password"},
        AgentRuntime(storage),
        dispatch=False,
        web_directory=web,
        downloads_directory=downloads,
    )
    baseline = json.loads(
        (
            Path(__file__).parent / "fixtures/archive/docs/evidence/2026-11-01-backend-inventory/routes-before.json"
        ).read_text()
    )
    expected_pairs = {(method, row["path"]) for row in baseline for method in row.get("methods", [])}
    expected_mounts = {row["path"] for row in baseline if row["kind"] == "Mount"}
    pairs, mounts = [], set()

    def walk(router):
        for route in router.routes:
            if hasattr(route, "original_router"):
                walk(route.original_router)
            elif hasattr(route, "methods"):
                pairs.extend((method, route.path) for method in route.methods)
            elif type(route).__name__ == "Mount":
                mounts.add(route.path)
            else:
                raise AssertionError(f"Unaccounted route type: {type(route).__name__}")

    walk(app.router)
    assert len(pairs) == len(set(pairs)) == 111
    assert set(pairs) == expected_pairs
    assert mounts == expected_mounts
