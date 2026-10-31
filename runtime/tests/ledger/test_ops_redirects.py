"""Administrative scripts reject redirects, including signed recovery object transfers."""

import importlib.util
import io
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace
import urllib.request

import pytest

from test_http_redirects import origins
from heteroes import http_safety
from heteroes.product import recovery
import heteroes.recovery_manifest as recovery_manifest

REPO = Path(__file__).resolve().parents[3]
ROOT = REPO / "scripts"


def load(name):
    spec = importlib.util.spec_from_file_location("probe_" + name.replace("-", "_"), ROOT / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("name", ["lab-login", "verify-public-lab", "check-public-replay", "recovery"])
def test_ops_client_redirect_rejected(name, origins, tmp_path, monkeypatch, capsys):
    origin, destination, received, state = origins
    module = load(name)
    if name == "recovery":
        credentials = tmp_path / "private.json"
        credentials.write_text(json.dumps({"users": {"admin": "synthetic-password"}}))
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "recovery.py",
                "restore",
                "--url",
                origin,
                "--runtime-root",
                str(REPO / "runtime"),
                "--point-id",
                "p",
                "--destination",
                str(tmp_path / "restored"),
                "--credentials-file",
                str(credentials),
            ],
        )
        assert module.main() == 1
        assert "redirect" in capsys.readouterr().err.lower()
    else:
        with pytest.raises(http_safety.RedirectError) as caught:
            if name == "lab-login":
                monkeypatch.setenv("HETEROES_ADMIN_PASSWORD", "synthetic-password")
                monkeypatch.setattr(module, "SESSION", tmp_path / "session.json")
                monkeypatch.setattr(sys, "argv", ["login.py", "--url", origin])
                module.main()
                assert not module.SESSION.exists()
            elif name == "verify-public-lab":
                module.get(origin, {"Authorization": "Bearer synthetic-token"})
            else:
                lab = module.Lab.__new__(module.Lab)
                lab.base, lab.headers = origin, {"Authorization": "Bearer synthetic-token"}
                lab.call("GET", "/experiments")
        assert "redirect" in str(caught.value).lower() and destination in str(caught.value)
        assert "synthetic-secret" not in str(caught.value)
    assert state["requests"] and received == []


@pytest.mark.parametrize("mode", ["upload", "download"])
def test_recovery_signed_object_redirect_rejected(mode, origins, tmp_path, monkeypatch, capsys):
    origin, destination, received, state = origins
    module = load("recovery")
    credentials = tmp_path / "credentials.json"
    credentials.write_text(json.dumps({"users": {"admin": "synthetic-password"}}))
    point = tmp_path / "point"
    point.mkdir()
    (point / "weights.bin").write_bytes(b"payload")
    manifest = {
        "formatVersion": 3,
        "runId": "run",
        "pointId": "point",
        "childWeightsSha256": "b" * 64,
        "files": {"weights.bin": {"sha256": "a" * 64, "sizeBytes": 7}},
    }
    monkeypatch.setattr(recovery, "verify_point", lambda *args, **kwargs: manifest)
    monkeypatch.setattr(recovery, "restore_point", lambda *args: None)
    monkeypatch.setattr(recovery, "safe_name", lambda *args: True)
    monkeypatch.setattr(recovery_manifest, "validate_manifest", lambda *args: None)
    real_urlopen = urllib.request.urlopen
    real_opener = http_safety.opener

    def dispatch(request, timeout=60, *, safe=False):
        url = request.full_url if isinstance(request, urllib.request.Request) else request
        if url.endswith("/auth/login"):
            value = {"accessToken": "synthetic-token"}
        elif url.endswith("/auth/logout"):
            value = {}
        elif url.endswith("/download-plan"):
            value = {"manifest": manifest, "objects": {"weights.bin": origin + "/object?capability=synthetic-secret"}}
        elif url.endswith("/recovery-import"):
            value = {
                "objects": [
                    {
                        "sha256": "a" * 64,
                        "sizeBytes": 7,
                        "mode": "single",
                        "url": origin + "/object?capability=synthetic-secret",
                    }
                ]
            }
        else:
            return (
                real_opener(proxy=False).open(request, timeout=timeout)
                if safe
                else real_urlopen(request, timeout=timeout)
            )
        return io.BytesIO(json.dumps(value).encode())

    monkeypatch.setattr(urllib.request, "urlopen", dispatch)
    monkeypatch.setattr(
        http_safety,
        "opener",
        lambda **kwargs: SimpleNamespace(open=lambda *args, **kw: dispatch(*args, **kw, safe=True)),
    )
    argv = [
        "recovery.py",
        "import" if mode == "upload" else "restore",
        "--url",
        "https://fixture.invalid",
        "--runtime-root",
        str(REPO / "runtime"),
        "--credentials-file",
        str(credentials),
    ]
    argv += (
        ["--point", str(point)]
        if mode == "upload"
        else ["--point-id", "point", "--destination", str(tmp_path / "restored")]
    )
    monkeypatch.setattr(sys, "argv", argv)
    assert module.main() == 1
    message = capsys.readouterr().err
    assert "redirect" in message.lower() and destination in message
    assert "synthetic-secret" not in message
    assert state["requests"] and received == []
