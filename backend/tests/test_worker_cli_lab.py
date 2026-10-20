"""`heteroes-worker join` and its boot-bound admission against the real lab routes (no GPU, no network)."""

import hashlib
import json
from pathlib import Path

from heteroes.product.worker_cli import LabError, Worker

from labkit import AGENT_COMMANDS, boot

EVIDENCE = Path(__file__).parents[2] / "docs/evidence/2026-10-19-v3-qualification-reference"
SELF_TEST = json.loads((EVIDENCE / "5070ti-qualify.json").read_text())["result"]  # a real Linux recipe v3 admission


def test_a_cli_worker_pairs_is_approved_boots_and_binds_its_admission_through_the_lab(lab, tmp_path):
    client, store, runtime, admin = lab
    root = tmp_path / "home"
    (root / "bundle").mkdir(parents=True)
    (root / "bundle" / "profile.json").write_text(
        json.dumps({"modelRevision": "r", "runtimeSha256": hashlib.sha256(b"").hexdigest(), "platforms": {"linux": {}}})
    )
    worker = Worker(root, say=lambda *_: None)
    worker.save_settings({"selfTest": SELF_TEST})

    def call(url, path, token, body, method=None):
        headers = {"Authorization": "Bearer " + token} if token else {}
        response = client.request(method or ("POST" if body is not None else "GET"), path, json=body, headers=headers)
        if response.status_code >= 400:
            raise LabError(response.status_code)
        return response.json()

    code = client.post("/api/v1/devices/pairing-codes", headers=admin).json()["code"]
    device = worker.join("http://testserver", code, "3060 at home", call=call)
    token = worker.paths()["token"].read_text()
    assert device["approvalStatus"] == "PENDING"
    assert (
        client.patch(
            "/api/v1/platform/devices/" + device["deviceId"],
            json={"approved": True, "workspaceId": "lab"},
            headers=admin,
        ).status_code
        == 200
    )
    agent = {"Authorization": "Bearer " + token, "X-HeteroES-Agent-Commands": AGENT_COMMANDS}
    boot(client, agent, "boot-1")

    class Bridge:
        def call(self, action):
            return {"bootId": "boot-1"}

    worker.declare_qualification(Bridge(), worker.settings(), token, call)

    [listed] = [
        d for d in client.get("/api/v1/platform/devices", headers=admin).json() if d["deviceId"] == device["deviceId"]
    ]
    assert listed["selfTest"]["recipeVersions"] == [3] and listed["selfTest"]["coordinator"] is False
