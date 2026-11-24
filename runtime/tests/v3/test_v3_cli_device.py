"""Owner rule (2026-11-24): the coordinator runs on a GPU whenever there is one; `auto` is the CLI default."""

import pytest

from heteroes.v3 import __main__ as cli


@pytest.mark.parametrize("available, expected", [(True, "cuda"), (False, "cpu")])
def test_auto_takes_the_gpu_when_there_is_one(monkeypatch, available, expected):
    import torch

    monkeypatch.setattr(torch.cuda, "is_available", lambda: available)
    assert cli.coordinator_device("auto") == expected


def test_an_explicit_device_is_kept(monkeypatch):
    import torch

    monkeypatch.setattr(torch.cuda, "is_available", lambda: True)
    assert cli.coordinator_device("cpu") == "cpu" and cli.coordinator_device("cuda") == "cuda"


@pytest.mark.parametrize("command", ["serve", "run"])
def test_serve_and_run_default_to_auto_and_resolve_it(monkeypatch, tmp_path, command):
    import torch

    seen = {}
    monkeypatch.setattr(torch.cuda, "is_available", lambda: True)
    spec = tmp_path / "spec.json"
    spec.write_text("{}")
    if command == "serve":
        from heteroes.v3 import distributed

        monkeypatch.setattr(distributed, "serve", lambda *a, **k: seen.update(device=k["device"]))
        cli.main(["serve", str(spec), "--out", str(tmp_path / "o")])
    else:
        import heteroes.v3.local

        monkeypatch.setattr(heteroes.v3.local, "run_local", lambda *a, **k: seen.update(device=k["device"]) or [])
        cli.main(["run", str(spec), "--out", str(tmp_path / "o")])
    assert seen == {"device": "cuda"}
