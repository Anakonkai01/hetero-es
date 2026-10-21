"""The private lab address is for members only (SECURITY-NOTES, owner decision 2026-10-21): the public health check no
longer returns it; a signed-in workspace member reads it from the capabilities."""

import json

from labkit import login


def test_health_hides_the_private_address_and_members_still_get_it(setup, tmp_path, monkeypatch):
    client, _, _ = setup
    (tmp_path / "private").mkdir()
    (tmp_path / "private" / "config.json").write_text(
        json.dumps({"apiUrl": "http://100.64.0.9:8790", "bulkApiUrl": "http://100.64.0.9:8791"})
    )
    monkeypatch.setenv("HETEROES_PRIVATE_CONFIG", str(tmp_path / "private"))
    health = client.get("/api/v1/health")
    assert health.status_code == 200 and "privateLabUrl" not in health.json()
    assert "100.64.0.9" not in health.text
    assert client.get("/api/v1/capabilities").status_code == 401
    member = login(client, "participant")
    assert client.get("/api/v1/capabilities", headers=member).json()["privateLabUrl"] == "http://100.64.0.9:8791"
