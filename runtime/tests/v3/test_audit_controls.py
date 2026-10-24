"""Audit coverage is an explicit frozen run setting, separate from recipe/update identity."""

import json

import pytest

from heteroes.sdk import ESConfig, ESTrainer
from heteroes.v3.lab_cli import managed_configuration
from heteroes.v3.local import run_local
from test_v3_local import assets, config_for


@pytest.mark.parametrize("rate", [0, 0.05, 1])
def test_sdk_and_lab_transport_preserve_audit_rate(rate):
    config = ESConfig(model_path="model", model_id="org/model", train_dataset="rows", audit_rate=rate)
    trainer = ESTrainer(config, scorer={"name": "last-integer"})
    spec = trainer.lab_spec()
    assert spec["auditRate"] == rate
    request = managed_configuration(spec, "coordinator", ["worker"], {"id": "model"}, {"datasetId": "data"})
    assert request["auditRate"] == rate


def test_default_audit_rate_is_five_percent():
    config = ESConfig(model_path="m", model_id="x", train_dataset="rows")
    assert ESTrainer(config, scorer={"name": "last-integer"}).config()["auditRate"] == 0.05


@pytest.mark.parametrize("rate", [True, False, -0.01, 1.01, "0.05", None, float("nan"), float("inf")])
def test_invalid_audit_rate_is_rejected_before_model_loading(rate, tmp_path, monkeypatch):
    import heteroes.v3.local as local

    with pytest.raises(ValueError, match="audit"):
        ESConfig(model_path="m", model_id="x", train_dataset="rows", audit_rate=rate)
    monkeypatch.setattr(
        local, "prepare", lambda *a, **k: pytest.fail("invalid audit rate must fail before model loading")
    )
    with pytest.raises(ValueError, match="audit"):
        run_local({"auditRate": rate}, tmp_path)


def test_config_controls_coverage_without_changing_recipe_plan_or_child(assets, tmp_path):
    results = []
    for rate in (0, 1):
        out = tmp_path / str(rate)
        summaries = run_local(config_for(assets, generations=1, auditRate=rate), out, workers=2, timeout_seconds=30)
        results.append((out, summaries[0]))
        frozen = json.loads((out / "audit-config.json").read_text())
        assert frozen == {"formatVersion": 1, "auditRate": rate}
    off, on = results[0][1], results[1][1]
    assert on["audits"]["selected"] == on["audits"]["completed"] == 4
    assert off.get("audits", {}).get("selected", 0) == 0
    assert off["audits"]["enabled"] is False
    assert off["record_hash"] == on["record_hash"] and off["child_sha256"] == on["child_sha256"]
    for name in ("recipe.json", "plan.json"):
        assert (results[0][0] / name).read_bytes() == (results[1][0] / name).read_bytes()


def test_restart_cannot_silently_change_frozen_audit_settings(tmp_path, monkeypatch):
    import heteroes.v3.local as local

    path = tmp_path / "audit-config.json"
    path.write_text(json.dumps({"formatVersion": 1, "auditRate": 0.05}))
    monkeypatch.setattr(
        local, "prepare", lambda *a, **k: pytest.fail("changed frozen settings must fail before loading")
    )
    with pytest.raises(ValueError, match="audit"):
        run_local({"auditRate": 1}, tmp_path)
    assert json.loads(path.read_text())["auditRate"] == 0.05


def test_invalid_existing_audit_receipt_is_preserved_and_rejected(tmp_path):
    from heteroes.v3.audit import freeze_audit_config

    path = tmp_path / "audit-config.json"
    path.write_text("null\n")
    with pytest.raises(ValueError, match="audit"):
        freeze_audit_config(tmp_path, 0.05)
    assert path.read_text() == "null\n"


@pytest.mark.parametrize("offset,selected", [(-1, True), (0, False), (1, False)])
def test_default_rate_keeps_exact_one_twentieth_hash_boundary(monkeypatch, offset, selected):
    import heteroes.v3.options as options

    class Digest:
        def hexdigest(self):
            return f"{2**256 // 20 + offset:064x}"

    monkeypatch.setattr(options.hashlib, "sha256", lambda value: Digest())
    assert options.audit_selected("candidate", 0.05) is selected
