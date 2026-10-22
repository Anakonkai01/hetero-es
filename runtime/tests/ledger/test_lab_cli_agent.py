"""Lab CLI uses the installed agent and preserves approval, workspace and explicit owner ON gates."""

import json

import pytest

from heteroes.product.files import write_json


@pytest.mark.parametrize("approved_workspace", ["lab", "another-lab"])
@pytest.mark.parametrize("offered_status", ["DRAFT", "COMPLETED"])
def test_lab_serving_uses_the_agent_and_never_approves_or_enables_it(
    tmp_path, monkeypatch, approved_workspace, offered_status
):
    from test_worker_cli import bundle, SELF_TEST
    from heteroes.v3 import lab_cli
    from heteroes.product import worker_cli, desktop_bridge

    worker = bundle(tmp_path)
    worker.install(run=lambda *a, **k: None)
    worker.save_settings(
        {
            "selfTest": {**SELF_TEST, "runtimeProfile": "desktop-v3"},
            "serverUrl": "http://lab.test",
            "device": {"deviceId": "d" * 32, "workerId": "cli"},
            "compute": worker.compute(True, "100.64.0.1"),
        }
    )
    worker.paths()["token"].write_text("fixture-device-secret")
    requests, offers, actions = [], [], []
    run_id = "f" * 32

    class API:
        def __init__(self, *args):
            pass

        def request(self, method, path, body=None):
            requests.append((method, path))
            if method == "GET" and path == "/api/v1/devices":
                return [{"deviceId": "d" * 32, "approvalStatus": "APPROVED", "workspaceId": approved_workspace}]
            if method == "POST" and path == f"/api/v1/experiments/{run_id}/submit":
                return {"status": "QUEUED"}
            raise AssertionError("Unexpected control request (approval/ON must stay owner-controlled)")

    class Bridge:
        def __init__(self, config, token):
            data = json.loads(config.read_text())
            assert "deviceToken" not in data and token == "fixture-device-secret"
            if offered_status == "DRAFT":
                write_json(worker.paths()["agentState"] / "runs" / run_id / "state.json", {"status": "COMPLETED"})

        def call(self, action):
            actions.append(action)
            return {"drained": True}

    def offer(*args):
        offers.append(args)
        return {"experimentId": run_id, "status": offered_status}

    from heteroes.product.files import read_json

    def read_state(path, default=None):
        if offered_status == "COMPLETED":
            raise AssertionError("A finished experiment must exit without waiting for local state")
        return read_json(path, default)

    monkeypatch.setattr(worker_cli, "Worker", lambda *_: worker)
    monkeypatch.setattr(worker, "declare_qualification", lambda *a: None)
    monkeypatch.setattr(desktop_bridge, "Bridge", Bridge)
    monkeypatch.setattr(lab_cli, "Lab", API)
    monkeypatch.setattr(lab_cli, "offer_experiment", offer)
    monkeypatch.setattr(lab_cli, "read_json", read_state)
    kwargs = dict(workspace="lab", host="100.64.0.1", worker_ids=["gpu"], device="cuda", approval_timeout=0)
    if approved_workspace == "lab":
        assert lab_cli.serve_lab({}, "http://lab.test", tmp_path / "offer", **kwargs) == 0
        assert len(offers) == 1
        assert (("POST", f"/api/v1/experiments/{run_id}/submit") in requests) == (offered_status == "DRAFT")
    else:
        with pytest.raises(ValueError, match="approval"):
            lab_cli.serve_lab({}, "http://lab.test", tmp_path / "offer", **kwargs)
        assert not offers
    assert actions == ["quit"]


def test_an_access_token_is_required_but_never_saved_in_an_api_receipt(monkeypatch):
    from heteroes.v3.lab_cli import Lab

    monkeypatch.delenv("HETEROES_LAB_ACCESS_TOKEN", raising=False)
    with pytest.raises(ValueError, match="HETEROES_LAB_ACCESS_TOKEN"):
        Lab("https://lab.test", "lab")


def test_a_dataset_upload_without_the_private_route_goes_over_the_public_link(monkeypatch, tmp_path):
    # owner 2026-10-22: no Tailscale by default; the private signed URL is used whenever it answers
    from heteroes.v3 import lab_cli

    monkeypatch.setenv("HETEROES_LAB_ACCESS_TOKEN", "token")
    sent = []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return b""

    monkeypatch.setattr(lab_cli.urllib.request, "urlopen", lambda request, timeout: sent.append(request) or Response())
    (tmp_path / "all.jsonl").write_text("{}\n")
    plan = {"url": "http://100.64.0.1:8002/u/1", "publicUrl": "https://lab.test/api/v1/public-upload/1", "headers": {}}
    lab = lab_cli.Lab("https://lab.test", "lab")
    lab.upload(plan, tmp_path / "all.jsonl", reachable=lambda url: False)
    lab.upload(plan, tmp_path / "all.jsonl", reachable=lambda url: True)
    lab.upload({**plan, "publicUrl": None}, tmp_path / "all.jsonl", reachable=lambda url: False)
    assert [r.full_url for r in sent] == [plan["publicUrl"], plan["url"], plan["url"]]
    assert all("Authorization" not in r.headers for r in sent), "the user's credential never goes to a storage link"
