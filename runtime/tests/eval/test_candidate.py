import hashlib
import importlib.util
import inspect
import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest
import torch
import torch.nn as nn

from heteroes.es.snapshot import RestoreError
from heteroes.eval import candidate as candidate_module
from heteroes.eval.candidate import model_weights_sha256, run_candidate
from heteroes.eval.generate import EvalRecord, EvalResult
from heteroes.eval.workload import EXAMPLES, workload_hash
from heteroes.model.schema import build_parameter_schema, resolve_tensors
from heteroes.noise.contracts import DEFAULT_CHUNK_ELEMENTS, ENGINE_VERSION

DEVICES = ["cpu"] + (["cuda"] if torch.cuda.is_available() else [])
SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "run_one_candidate.py"
PROBE_JSON = (
    Path(__file__).resolve().parents[2] / "artifacts" / "probes" / "2026-09-29" / "probe_5070ti.json"
)


class HalfToy(nn.Module):
    # FP16 model in miniature: embed.weight (40, tied with head.weight), fc.weight (16), fc.bias (4)
    def __init__(self):
        super().__init__()
        self.embed = nn.Embedding(10, 4)
        self.head = nn.Linear(4, 10, bias=False)
        self.head.weight = self.embed.weight
        self.fc = nn.Linear(4, 4)
        self.half()


def make_model(device="cpu"):
    torch.manual_seed(0)
    return HalfToy().to(device)


def bits(model):
    return [p.detach().cpu().reshape(-1).view(torch.int16).clone() for p in model.parameters()]


def same_bits(model, reference):
    return all(torch.equal(a, b) for a, b in zip(bits(model), reference))


def oracle_digest(model, schema):
    # independent: the raw bytes of each tensor in schema order, written by hand
    digest = hashlib.sha256()
    for tensor in resolve_tensors(model, schema):
        digest.update(tensor.detach().cpu().numpy().reshape(-1).view(np.int16).tobytes())
    return digest.hexdigest()


# ---------------------------------------------------------------------------
# a fake evaluation that looks at the weights it is given, and records when it is called
# ---------------------------------------------------------------------------

class Recorder:
    def __init__(self, monkeypatch, model, schema):
        self.events = []
        self.model, self.schema = model, schema
        real_snapshot, real_perturb, real_restore = (
            candidate_module.take_snapshot, candidate_module.perturb_model_, candidate_module.restore_from_snapshot_,
        )

        def snapshot(*args, **kwargs):
            self.events.append("snapshot")
            return real_snapshot(*args, **kwargs)

        def perturb(*args, **kwargs):
            bound = inspect.signature(real_perturb).bind(*args, **kwargs)
            bound.apply_defaults()
            self.events.append(("perturb", dict(bound.arguments)))
            return real_perturb(*args, **kwargs)

        def restore(*args, **kwargs):
            self.events.append("restore")
            return real_restore(*args, **kwargs)

        monkeypatch.setattr(candidate_module, "take_snapshot", snapshot)
        monkeypatch.setattr(candidate_module, "perturb_model_", perturb)
        monkeypatch.setattr(candidate_module, "restore_from_snapshot_", restore)
        monkeypatch.setattr(candidate_module, "evaluate_model", self.evaluate)

    def evaluate(self, model, tokenizer):
        # the "answer" is the fingerprint of the weights at the moment of the call
        fingerprint = oracle_digest(model, self.schema)[:12]
        self.events.append(("evaluate", fingerprint))
        record = EvalRecord(EXAMPLES[0].question, EXAMPLES[0].answer, fingerprint, None, 0.0)
        return EvalResult(0.0, (record,))

    def names(self):
        return [e if isinstance(e, str) else e[0] for e in self.events]


@pytest.fixture
def setup(monkeypatch):
    model = make_model()
    schema = build_parameter_schema(model)
    return model, schema, Recorder(monkeypatch, model, schema)


# ---------------------------------------------------------------------------
# model_weights_sha256
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("device", DEVICES)
def test_weights_digest_matches_the_hand_written_oracle(device):
    model = make_model(device)
    schema = build_parameter_schema(model)

    assert model_weights_sha256(model, schema) == oracle_digest(model, schema)


def test_weights_digest_sees_one_flipped_bit_and_a_sign_of_zero():
    model = make_model()
    schema = build_parameter_schema(model)
    before = model_weights_sha256(model, schema)
    bias = resolve_tensors(model, schema)[2]

    bias.detach().view(torch.int16)[1] = bias.detach().view(torch.int16)[1] ^ 1
    assert model_weights_sha256(model, schema) != before

    with torch.no_grad():
        bias[2] = 0.0
    positive_zero = model_weights_sha256(model, schema)
    with torch.no_grad():
        bias[2] = -0.0
    assert model_weights_sha256(model, schema) != positive_zero


def test_weights_digest_counts_a_tied_tensor_once():
    model = make_model()
    schema = build_parameter_schema(model)
    expected = hashlib.sha256()
    for tensor in (model.embed.weight, model.fc.weight, model.fc.bias):
        expected.update(tensor.detach().numpy().reshape(-1).view(np.int16).tobytes())

    assert model_weights_sha256(model, schema) == expected.hexdigest()


# ---------------------------------------------------------------------------
# the order of the steps, and what the evaluations see
# ---------------------------------------------------------------------------

def test_steps_run_in_the_right_order_and_each_evaluation_sees_the_right_model(setup):
    model, schema, recorder = setup
    original = oracle_digest(model, schema)

    result = run_candidate(model, None, schema, seed=3, sigma=5e-2, chunk_elements=8)

    assert recorder.names() == ["snapshot", "evaluate", "perturb", "evaluate", "restore", "evaluate"]
    seen = [e[1] for e in recorder.events if isinstance(e, tuple) and e[0] == "evaluate"]
    assert seen[0] == original[:12]          # base: the original weights
    assert seen[1] != original[:12]          # candidate: perturbed weights
    assert seen[2] == original[:12]          # after restore: the original weights again
    assert result["evaluation"]["base"] == result["evaluation"]["restored"]
    assert result["evaluation"]["base"] != result["evaluation"]["candidate"]


def test_seed_sigma_and_chunk_elements_reach_the_perturbation(setup):
    model, schema, recorder = setup

    run_candidate(model, None, schema, seed=11, sigma=0.0123, chunk_elements=8)

    (_, arguments) = next(e for e in recorder.events if isinstance(e, tuple) and e[0] == "perturb")
    assert (arguments["candidate_seed"], arguments["sigma"], arguments["chunk_elements"]) == (11, 0.0123, 8)
    assert arguments["schema"] is schema


def test_the_default_chunk_size_is_the_contract_value(setup):
    model, schema, recorder = setup

    result = run_candidate(model, None, schema, seed=1, sigma=1e-2)

    assert result["chunk_elements"] == DEFAULT_CHUNK_ELEMENTS


# ---------------------------------------------------------------------------
# the weights: fingerprints and restore
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("device", DEVICES)
def test_fingerprints_show_perturbation_and_exact_restore(device, monkeypatch):
    model = make_model(device)
    schema = build_parameter_schema(model)
    Recorder(monkeypatch, model, schema)
    reference = bits(model)
    original = oracle_digest(model, schema)

    result = run_candidate(model, None, schema, seed=3, sigma=5e-2, chunk_elements=8)

    digests = result["weights_sha256"]
    assert digests["original"] == digests["restored"] == original
    assert digests["perturbed"] != original
    assert result["restored_equals_original"] is True
    assert same_bits(model, reference)


# ---------------------------------------------------------------------------
# failures: raised, and the model comes back
# ---------------------------------------------------------------------------

def test_a_failure_while_evaluating_the_candidate_restores_the_model_and_is_raised(setup, monkeypatch):
    model, schema, recorder = setup
    reference = bits(model)
    real_evaluate = recorder.evaluate
    calls = []

    def failing(model, tokenizer):
        calls.append(1)
        if len(calls) == 2:           # the second evaluation is the candidate
            raise RuntimeError("CUDA out of memory")
        return real_evaluate(model, tokenizer)

    monkeypatch.setattr(candidate_module, "evaluate_model", failing)

    with pytest.raises(RuntimeError, match="out of memory"):
        run_candidate(model, None, schema, seed=3, sigma=5e-2, chunk_elements=8)

    assert same_bits(model, reference)
    assert recorder.names()[-1] == "restore"
    assert len(calls) == 2            # no evaluation after the failure


def test_a_failure_of_the_base_evaluation_stops_before_any_perturbation(setup, monkeypatch):
    model, schema, recorder = setup
    reference = bits(model)

    def failing(model, tokenizer):
        raise RuntimeError("tokenizer broke")

    monkeypatch.setattr(candidate_module, "evaluate_model", failing)

    with pytest.raises(RuntimeError, match="tokenizer"):
        run_candidate(model, None, schema, seed=3, sigma=5e-2, chunk_elements=8)

    assert "perturb" not in recorder.names()
    assert same_bits(model, reference)


@pytest.mark.parametrize("bad_sigma", [float("nan"), float("inf")])
def test_a_bad_sigma_is_raised_and_nothing_is_evaluated_as_a_candidate(setup, bad_sigma):
    model, schema, recorder = setup
    reference = bits(model)

    with pytest.raises(ValueError):
        run_candidate(model, None, schema, seed=3, sigma=bad_sigma, chunk_elements=8)

    assert recorder.names().count("evaluate") == 1     # only the base evaluation
    assert same_bits(model, reference)


def test_a_restore_that_silently_does_nothing_is_seen_by_the_fingerprints(setup, monkeypatch):
    # restore_from_snapshot_ verifies itself, but the record has its own, independent check.
    model, schema, _ = setup
    monkeypatch.setattr(candidate_module, "restore_from_snapshot_", lambda *args, **kwargs: None)

    result = run_candidate(model, None, schema, seed=3, sigma=5e-2, chunk_elements=8)

    assert result["restored_equals_original"] is False
    assert result["weights_sha256"]["restored"] == result["weights_sha256"]["perturbed"]
    assert result["weights_sha256"]["restored"] != result["weights_sha256"]["original"]


def test_a_failed_restore_is_raised_as_restore_error(setup, monkeypatch):
    model, schema, recorder = setup

    def broken(*args, **kwargs):
        raise RestoreError("tensors differ")

    monkeypatch.setattr(candidate_module, "restore_from_snapshot_", broken)

    with pytest.raises(RestoreError):
        run_candidate(model, None, schema, seed=3, sigma=5e-2, chunk_elements=8)


# ---------------------------------------------------------------------------
# the record
# ---------------------------------------------------------------------------

def test_the_result_is_plain_json_with_exactly_the_agreed_keys(setup):
    model, schema, _ = setup

    result = run_candidate(model, None, schema, seed=3, sigma=1e-3, chunk_elements=8)

    assert json.loads(json.dumps(result)) == result      # nothing that JSON cannot hold
    assert set(result) == {
        "seed", "sigma", "sigma_float32", "chunk_elements", "schema_hash", "engine_version", "workload_hash",
        "weights_sha256", "restored_equals_original", "evaluation", "timing_seconds", "gpu_memory",
    }
    assert set(result["evaluation"]) == {"base", "candidate", "restored"}
    assert set(result["weights_sha256"]) == {"original", "perturbed", "restored"}
    assert set(result["evaluation"]["base"]) == {"mean_reward", "records"}


def test_the_record_names_the_candidate_and_the_recipe(setup):
    model, schema, _ = setup

    result = run_candidate(model, None, schema, seed=3, sigma=1e-3, chunk_elements=8)

    assert result["seed"] == 3 and result["sigma"] == 1e-3
    assert result["sigma_float32"] == float(np.float32(1e-3)) != 1e-3   # 1e-3 is not exact in binary
    assert result["schema_hash"] == schema.hash
    assert result["engine_version"] == ENGINE_VERSION == "numpy_pcg64_normal_f32_to_f16_v1"
    assert result["workload_hash"] == workload_hash()


def test_timings_cover_every_step_and_there_is_no_gpu_record_on_the_cpu(setup):
    model, schema, _ = setup

    result = run_candidate(model, None, schema, seed=3, sigma=1e-3, chunk_elements=8)

    assert set(result["timing_seconds"]) == {
        "hash_original", "snapshot", "evaluate_base", "perturb", "hash_perturbed", "evaluate_candidate",
        "restore", "hash_restored", "evaluate_restored",
    }
    assert all(isinstance(v, float) and v >= 0 for v in result["timing_seconds"].values())
    assert result["gpu_memory"] is None


@pytest.mark.skipif("cuda" not in DEVICES, reason="needs a CUDA GPU")
def test_on_a_gpu_the_peak_memory_is_recorded(monkeypatch):
    model = make_model("cuda")
    schema = build_parameter_schema(model)
    Recorder(monkeypatch, model, schema)

    result = run_candidate(model, None, schema, seed=3, sigma=1e-3, chunk_elements=8)

    memory = result["gpu_memory"]
    assert set(memory) == {"baseline_allocated_bytes", "peak_allocated_bytes"}
    assert memory["peak_allocated_bytes"] >= memory["baseline_allocated_bytes"] > 0


@pytest.mark.skipif("cuda" not in DEVICES, reason="needs a CUDA GPU")
def test_the_peak_memory_does_not_include_what_happened_before_the_run(monkeypatch):
    model = make_model("cuda")
    schema = build_parameter_schema(model)
    Recorder(monkeypatch, model, schema)
    spike = torch.empty(64 * 2**20, dtype=torch.uint8, device="cuda")   # a 64 MiB peak before the run
    del spike

    result = run_candidate(model, None, schema, seed=3, sigma=1e-3, chunk_elements=8)

    memory = result["gpu_memory"]
    assert memory["peak_allocated_bytes"] - memory["baseline_allocated_bytes"] < 32 * 2**20


# ---------------------------------------------------------------------------
# the real model: HETEROES_QWEN_PINNED_PATH=<snapshot dir of Qwen2.5-0.5B-Instruct @ 7ae55760...>
# ---------------------------------------------------------------------------

PINNED_PATH = os.environ.get("HETEROES_QWEN_PINNED_PATH")
needs_model = pytest.mark.skipif(
    PINNED_PATH is None or not torch.cuda.is_available(),
    reason="set HETEROES_QWEN_PINNED_PATH and use a CUDA GPU to run the real-model checks",
)
PRODUCTION_SCHEMA_HASH = "0b21250e331398a266785dc473da3a8b8f5e8f98fa15e9044637d742eb7845ec"
PROBE_WORKLOAD_HASH = "cad822bc1e65a9ec37d948e5415cff22c70f96500e2043e6299bbdd5cea0b8d5"
O2_PERTURBED_HASH_PREFIX = "8aa3eb9af895cb4a"


def comparable(result):
    # everything except the clock and the memory
    return {k: v for k, v in result.items() if k not in ("timing_seconds", "gpu_memory")}


@pytest.fixture(scope="module")
def qwen():
    from transformers import AutoModelForCausalLM, AutoTokenizer

    model = AutoModelForCausalLM.from_pretrained(PINNED_PATH, dtype=torch.float16).to("cuda")
    return model, AutoTokenizer.from_pretrained(PINNED_PATH)


@needs_model
def test_qwen_candidate_matches_all_the_recorded_evidence(qwen):
    model, tokenizer = qwen
    schema = build_parameter_schema(model)
    recorded = json.loads(PROBE_JSON.read_text(encoding="utf-8"))["base_evaluation"]

    result = run_candidate(model, tokenizer, schema, seed=0, sigma=1e-3)

    assert result["schema_hash"] == PRODUCTION_SCHEMA_HASH
    assert result["workload_hash"] == PROBE_WORKLOAD_HASH
    assert result["weights_sha256"]["perturbed"].startswith(O2_PERTURBED_HASH_PREFIX)
    assert result["weights_sha256"]["restored"] == result["weights_sha256"]["original"]
    assert result["restored_equals_original"] is True
    base = result["evaluation"]["base"]
    assert base["mean_reward"] == recorded["mean_reward"] == 0.25
    assert [r["output_text"] for r in base["records"]] == [r["output_text"] for r in recorded["records"]]
    assert result["evaluation"]["restored"] == base                      # the restored model answers like the base
    assert result["evaluation"]["candidate"] != base                     # the perturbation is visible


@needs_model
def test_qwen_candidate_is_repeatable_in_one_process(qwen):
    model, tokenizer = qwen
    schema = build_parameter_schema(model)

    first = run_candidate(model, tokenizer, schema, seed=0, sigma=1e-3)
    second = run_candidate(model, tokenizer, schema, seed=0, sigma=1e-3)

    assert comparable(first) == comparable(second)


@needs_model
def test_the_script_writes_a_complete_json_record(tmp_path):
    output = tmp_path / "candidate.json"

    completed = subprocess.run(
        [sys.executable, str(SCRIPT), "--model-path", PINNED_PATH, "--seed", "1", "--sigma", "2e-3",
         "--repeat", "2", "--output", str(output)],
        capture_output=True, text=True,
    )

    assert completed.returncode == 0, completed.stderr[-2000:]
    record = json.loads(output.read_text(encoding="utf-8"))
    assert set(record) == {"format_version", "environment", "code", "model", "noise_selftest", "recipe", "recipe_hash",
                           "descriptor", "runs", "repeat_identical"}
    assert record["format_version"] == 2
    assert len(record["runs"]) == 2
    assert record["repeat_identical"] is True
    assert set(record["code"]) == {"git_commit", "git_dirty"}
    assert record["model"]["revision"] == record["model"]["tokenizer_revision"] == "7ae557604adf67be50417f59c2c2f167def9a775"
    assert record["model"]["dtype"] == "torch.float16"
    assert len(record["model"]["generation_config_sha256"]) == 64
    assert record["model"]["generation_config_sha256"] != record["model"]["generation_config_raw_sha256"]  # set values vs the raw dict
    # the manifest: the recipe, its hash, the descriptor and the self-test
    from heteroes.manifest import CandidateDescriptor, Recipe, effective_generation_config
    from heteroes.noise.selftest import EXPECTED_NOISE_FINGERPRINT
    recipe = Recipe.from_dict(record["recipe"])
    assert recipe.hash == record["recipe_hash"]
    assert recipe.sigma == 2e-3 and recipe.schema_hash == record["runs"][0]["schema_hash"]
    assert recipe.generation_config_sha256 == record["model"]["generation_config_sha256"]
    assert recipe.noise_fingerprint == EXPECTED_NOISE_FINGERPRINT
    descriptor = CandidateDescriptor.from_dict(record["descriptor"])
    assert descriptor.recipe_hash == recipe.hash and descriptor.seed == 1 and descriptor.experiment_id == "regression"
    assert descriptor.parent_weights_sha256 == record["runs"][0]["weights_sha256"]["original"]
    assert record["noise_selftest"]["passed"] is True
    assert record["noise_selftest"]["computed_fingerprint"] == EXPECTED_NOISE_FINGERPRINT
    assert {"torch", "numpy", "transformers", "python", "gpu_name", "hostname"} <= set(record["environment"])
    for run in record["runs"]:
        assert (run["seed"], run["sigma"]) == (1, 2e-3)       # the options really reach the candidate
        assert run["weights_sha256"]["perturbed"] != run["weights_sha256"]["original"]
        assert run["restored_equals_original"] is True


def test_the_script_refuses_a_model_that_is_not_the_pinned_revision(tmp_path):
    other = tmp_path / "not_a_revision"
    other.mkdir()

    completed = subprocess.run(
        [sys.executable, str(SCRIPT), "--model-path", str(other), "--output", str(tmp_path / "x.json")],
        capture_output=True, text=True,
    )

    assert completed.returncode == 2          # a deliberate refusal, not a crash
    assert not (tmp_path / "x.json").exists()
    assert "pinned revision" in completed.stderr


def test_the_script_refuses_to_overwrite_an_existing_output_file(tmp_path):
    model_dir = tmp_path / "7ae557604adf67be50417f59c2c2f167def9a775"
    model_dir.mkdir()
    output = tmp_path / "evidence.json"
    output.write_text("keep me", encoding="utf-8")

    completed = subprocess.run(
        [sys.executable, str(SCRIPT), "--model-path", str(model_dir), "--output", str(output)],
        capture_output=True, text=True,
    )

    assert completed.returncode == 2
    assert "already exists" in completed.stderr
    assert output.read_text(encoding="utf-8") == "keep me"


def load_script():
    spec = importlib.util.spec_from_file_location("run_one_candidate", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def fake_run(**changes):
    run = {"seed": 0, "weights_sha256": {"original": "a", "perturbed": "b", "restored": "a"},
           "evaluation": {"base": {"mean_reward": 0.25, "records": []}},
           "timing_seconds": {"snapshot": 1.0}, "gpu_memory": {"peak_allocated_bytes": 1}}
    run.update(changes)
    return run


def test_runs_that_differ_only_in_time_and_memory_are_identical():
    script = load_script()
    first = fake_run()
    second = fake_run(timing_seconds={"snapshot": 9.0}, gpu_memory={"peak_allocated_bytes": 99})

    assert script.runs_identical([first, second]) is True
    assert script.runs_identical([first]) is True


@pytest.mark.parametrize(
    "change",
    [
        dict(weights_sha256={"original": "a", "perturbed": "c", "restored": "a"}),
        dict(evaluation={"base": {"mean_reward": 0.5, "records": []}}),
        dict(seed=1),
    ],
)
def test_runs_that_differ_in_anything_else_are_not_identical(change):
    script = load_script()

    assert script.runs_identical([fake_run(), fake_run(**change)]) is False
    assert script.runs_identical([fake_run(), fake_run(), fake_run(**change)]) is False


@pytest.mark.parametrize("status, dirty", [("", False), (" M file.py\n?? new.py", True)])
def test_code_info_reports_the_commit_and_whether_the_tree_is_dirty(monkeypatch, status, dirty):
    script = load_script()
    answers = {("git", "rev-parse", "HEAD"): "abc123", ("git", "status", "--porcelain"): status}
    monkeypatch.setattr(script, "run_command", lambda arguments: answers[tuple(arguments)])

    assert script.code_info() == {"git_commit": "abc123", "git_dirty": dirty}


def test_code_info_without_git_gives_unknown_not_clean(monkeypatch):
    script = load_script()
    monkeypatch.setattr(script, "run_command", lambda arguments: None)

    assert script.code_info() == {"git_commit": None, "git_dirty": None}
