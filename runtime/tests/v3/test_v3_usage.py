"""Usage is optional non-numerical metadata: retries cannot double bill or change canonical records."""

import copy
import json

import pytest

from heteroes.manifest import CandidateDescriptor
from heteroes.ledger import Ledger, SubmitOutcome
from heteroes.worker import WorkerClient, local_transport
from heteroes.worker_api import WorkerAPI, completions_sha256
from test_v3_local import assets, config_for


def usage(device="cuda", wall=1.25):
    return {"formatVersion": 1, "generatedTokens": [3, 2], "device": device, "wallSeconds": wall}


def test_token_counts_include_the_first_eos_and_exclude_only_padding_after_it():
    from heteroes.v3.usage import generated_token_count

    assert generated_token_count([4, 5, 9, 0, 0], {9}) == 3
    assert generated_token_count([4, 5], {9}) == 2
    assert generated_token_count([9, 9, 9], {9}) == 1  # EOS can also be the pad token
    assert generated_token_count([], {9}) == 0
    assert generated_token_count([0, 4], {9}) == 2  # a generated pad ID before EOS is still a real generated token


def test_token_rows_are_opt_in_so_legacy_evaluation_serialization_does_not_change(assets):
    from heteroes.v3.model import load, file_manifest
    from heteroes.study.evaluation import generate_rows

    model, tokenizer = load(assets / "model", file_manifest(assets / "model"), "cpu")
    rows = [{"prompt": "What is 17 plus 24?", "answer": "41"}]
    evaluation = {"systemPrompt": None, "maxNewTokens": 4}
    old = generate_rows(model.float(), tokenizer, rows, evaluation)
    counted = generate_rows(model, tokenizer, rows, evaluation, count_tokens=True)
    assert "generatedTokens" not in old[0]
    assert {k: v for k, v in counted[0].items() if k != "generatedTokens"} == old[0]
    assert 1 <= counted[0]["generatedTokens"] <= 4


def test_usage_store_is_idempotent_separates_audits_and_marks_missing_reports(tmp_path):
    from heteroes.v3.usage import UsageStore

    store = UsageStore(tmp_path / "usage.sqlite")
    descriptor = CandidateDescriptor("a" * 64, "b" * 64, "usage", 0, 0, 5)
    store.record(descriptor, 1, "worker", usage(), "candidate")
    store.record(descriptor, 1, "worker", usage(), "candidate")
    store.record(descriptor, 1, "auditor", usage("cpu", 2), "audit")
    summary = store.summary(0, expected_candidates=2, expected_audits=1)
    assert summary["generatedTokens"] == 5 and summary["auditGeneratedTokens"] == 5
    assert summary["workerGpuSeconds"] == 1.25 and summary["workerWallSeconds"] == 3.25
    assert summary["reportedCandidates"] == 1 and summary["reportedAudits"] == 1 and summary["partial"]
    assert not store.summary(0, expected_candidates=1, expected_audits=1)["partial"]
    with pytest.raises(ValueError, match="changed"):
        store.record(descriptor, 1, "worker", usage(wall=99), "candidate")
    assert store.summary(0, expected_candidates=1, expected_audits=1)["workerGpuSeconds"] == 1.25


def test_optional_usage_reaches_the_sidecar_without_changing_text_identity_or_retry_result(tmp_path):
    from heteroes.v3.usage import UsageStore, CompletionBatch

    with Ledger(tmp_path / "ledger.sqlite") as ledger:
        descriptor = CandidateDescriptor("a" * 64, "b" * 64, "usage", 0, 0, 5)
        ledger.open_generation([descriptor])
        store = UsageStore(tmp_path / "usage.sqlite")
        api = WorkerAPI(ledger, "usage", 0, 60, scorer=lambda d, texts: 0.75, usage_sink=store.record)
        client = WorkerClient("worker", local_transport(api), usage_reporting=True)
        work = client.lease().assignment
        batch = CompletionBatch(("a", "b"), usage())
        assert completions_sha256(batch) == completions_sha256(["a", "b"])
        assert client.submit_completions(work, batch) is SubmitOutcome.COMMITTED
        assert client.submit_completions(work, batch) is SubmitOutcome.ALREADY_COMMITTED
        assert ledger.get_completions(descriptor.candidate_id) == (completions_sha256(["a", "b"]), ["a", "b"])
        assert store.summary(0, expected_candidates=1, expected_audits=0)["generatedTokens"] == 5
        bad = {
            **work.payload(),
            "completions": ["a", "b"],
            "completions_sha256": completions_sha256(["a", "b"]),
            "usage": {**usage(), "generatedTokens": [True, 2]},
        }
        assert api.handle("submit_result", bad)["error"]["code"] == "bad_request"


def test_a_usage_sink_failure_cannot_turn_a_committed_reward_into_failure(tmp_path):
    from heteroes.v3.usage import CompletionBatch

    def broken(*args):
        raise OSError("disk unavailable")

    with Ledger(tmp_path / "ledger.sqlite") as ledger:
        descriptor = CandidateDescriptor("a" * 64, "b" * 64, "usage", 0, 0, 5)
        ledger.open_generation([descriptor])
        api = WorkerAPI(ledger, "usage", 0, 60, scorer=lambda d, texts: 0.75, usage_sink=broken)
        client = WorkerClient("worker", local_transport(api), usage_reporting=True)
        assert (
            client.submit_completions(client.lease().assignment, CompletionBatch(["a", "b"], usage()))
            is SubmitOutcome.COMMITTED
        )
        assert ledger.get_candidate(descriptor.candidate_id).result.reward == 0.75
        assert api.usage_errors == 1


def test_workers_do_not_send_usage_to_coordinators_that_did_not_advertise_it():
    from heteroes.v3.usage import CompletionBatch
    from heteroes.worker import Assignment

    descriptor = CandidateDescriptor("a" * 64, "b" * 64, "usage", 0, 0, 5)
    assignment = Assignment(descriptor, 1, "fixture-lease", 100)
    sent = []

    def transport(operation, payload):
        sent.append(payload)
        return {"ok": True, "outcome": "COMMITTED"}

    batch = CompletionBatch(["a", "b"], usage())
    old = WorkerClient("worker", transport)
    old.submit_completions(assignment, batch)
    new = WorkerClient("worker", transport, usage_reporting=True)
    new.submit_completions(assignment, batch)
    assert "usage" not in sent[0] and sent[1]["usage"] == usage()
    assert {k: v for k, v in sent[1].items() if k != "usage"} == sent[0]


def test_real_candidate_usage_is_recorded_and_old_workers_remain_numerically_identical(assets, tmp_path, monkeypatch):
    from heteroes.v3.local import run_local
    from heteroes.v3.usage import UsageStore
    from heteroes.executor import CandidateExecutor

    config = config_for(assets, generations=1, candidateSeedNamespace="usage-fixture")
    first = run_local(config, tmp_path / "new", timeout_seconds=20, audit_rate=0)
    recorded = first[0]["usage"]
    assert not recorded["partial"] and recorded["reportedCandidates"] == config["population"]
    assert (
        0 < recorded["generatedTokens"] <= config["population"] * config["data"]["batchSize"] * config["maxNewTokens"]
    )
    assert recorded["workerGpuSeconds"] == 0  # CPU execution is never reported as GPU time
    original = CandidateExecutor.__call__
    monkeypatch.setattr(CandidateExecutor, "__call__", lambda self, d: tuple(original(self, d)))
    old = run_local(config, tmp_path / "old", timeout_seconds=20, audit_rate=0)
    assert first[0]["record_hash"] == old[0]["record_hash"] and first[0]["child_sha256"] == old[0]["child_sha256"]
    assert old[0]["usage"]["partial"] and old[0]["usage"]["reportedCandidates"] == 0


def test_coordinator_update_gpu_time_excludes_writing_and_hashing_the_child_weights(assets, tmp_path, monkeypatch):
    import time

    import torch

    import heteroes.coordinator as coordinator
    from heteroes.v3.local import run_local

    publish = coordinator.prepare_publication

    def slow_publication(*args, **kwargs):
        time.sleep(0.5)  # stands in for writing and hashing a full model on disk
        return publish(*args, **kwargs)

    monkeypatch.setattr(coordinator, "prepare_publication", slow_publication)
    monkeypatch.setattr(coordinator.Coordinator, "_model_on_gpu", lambda self: True)
    monkeypatch.setattr(torch.cuda, "synchronize", lambda *a, **kw: None)
    config = config_for(assets, generations=1, candidateSeedNamespace="usage-update-window")
    recorded = run_local(config, tmp_path / "run", timeout_seconds=20, audit_rate=0)[0]["usage"]
    assert recorded["recordedUpdates"] == 1
    assert 0 < recorded["coordinatorUpdateGpuSeconds"] < 0.4
