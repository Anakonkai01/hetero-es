import copy
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "compare_candidate_records.py"
EVIDENCE = Path(__file__).resolve().parents[2] / "artifacts" / "regression" / "2026-10-05-one-candidate"


def load_script():
    spec = importlib.util.spec_from_file_location("compare_candidate_records", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def evaluation(texts, reward):
    return {"mean_reward": reward, "records": [
        {"question": f"q{i}", "expected": 1, "output_text": t, "prediction": None, "reward": 0.0} for i, t in enumerate(texts)]}


def make_record(**changes):
    run = {
        "seed": 0, "sigma": 0.001, "sigma_float32": 0.0010000000474974513, "chunk_elements": 262144,
        "schema_hash": "a" * 64, "engine_version": "numpy_pcg64_normal_f32_to_f16_v1", "workload_hash": "b" * 64,
        "weights_sha256": {"original": "o" * 64, "perturbed": "p" * 64, "restored": "o" * 64},
        "restored_equals_original": True,
        "evaluation": {"base": evaluation(["1", "2"], 0.25), "candidate": evaluation(["1", "3"], 0.3), "restored": evaluation(["1", "2"], 0.25)},
        "timing_seconds": {}, "gpu_memory": None,
    }
    record = {
        "format_version": 1,
        "environment": {"hostname": "m", "gpu_name": "g", "gpu_capability": [7, 5], "python": "3.12", "torch": "2", "torch_cuda": "12", "numpy": "2", "transformers": "5", "nvidia_driver": "1"},
        "code": {"git_commit": "c" * 40, "git_dirty": False},
        "model": {"revision": "1" * 40, "tokenizer_revision": "1" * 40, "dtype": "torch.float16", "generation_config_sha256": "g" * 64,
                  "generation_config": {"do_sample": True, "temperature": 0.7, "repetition_penalty": 1.1, "max_length": None, "transformers_version": "5.5.0"}},
        "runs": [run, copy.deepcopy(run)], "repeat_identical": True,
    }
    for path, value in changes.items():
        target = record
        keys = path.split(".")
        for key in keys[:-1]:
            target = target[int(key)] if key.isdigit() else target[key]
        target[int(keys[-1]) if keys[-1].isdigit() else keys[-1]] = value
    return record


def test_two_identical_records_are_equal_everywhere():
    report, ok = load_script().compare(make_record(), make_record(), "a.json", "b.json")

    assert ok is True
    assert "DIFFERENT" not in report and "NO " not in report
    assert report.endswith("RESULT: every MUST BE EQUAL line is equal")


@pytest.mark.parametrize(
    "change",
    [
        {"runs.0.schema_hash": "x" * 64},
        {"runs.0.workload_hash": "x" * 64},
        {"runs.0.engine_version": "v2"},
        {"runs.0.chunk_elements": 1},
        {"runs.0.seed": 1},
        {"runs.0.sigma": 0.002},
        {"runs.0.sigma_float32": 0.002},
        {"runs.0.weights_sha256.original": "x" * 64},
        {"runs.0.weights_sha256.perturbed": "x" * 64},
        {"runs.0.weights_sha256.restored": "x" * 64},
        {"model.revision": "x" * 40},
        {"model.tokenizer_revision": "x" * 40},
        {"model.dtype": "torch.bfloat16"},
        {"model.generation_config.repetition_penalty": 1.0},
        {"model.generation_config.temperature": 0.9},
    ],
)
def test_a_difference_in_what_must_be_equal_is_reported_and_fails(change):
    report, ok = load_script().compare(make_record(), make_record(**change))

    assert ok is False
    assert "DIFFERENT" in report
    assert report.endswith("AT LEAST ONE MUST-BE-EQUAL LINE DIFFERS")


@pytest.mark.parametrize(
    "change",
    [
        {"runs.0.restored_equals_original": False},
        {"repeat_identical": False},
        {"runs.1.evaluation.restored": evaluation(["9", "9"], 0.0)},
    ],
)
def test_what_must_hold_on_each_machine_by_itself_is_checked_for_both_files(change):
    script = load_script()

    assert script.compare(make_record(**change), make_record())[1] is False
    assert script.compare(make_record(), make_record(**change))[1] is False


def test_different_predictions_are_listed_question_by_question_and_do_not_fail():
    other = make_record(**{"runs.0.evaluation.candidate": evaluation(["1", "4"], 0.5)})

    report, ok = load_script().compare(make_record(), other)

    assert ok is True                                   # a measured difference is not an error by itself
    assert "candidate: reward A 0.3 | B 0.5; 1 of 2 output texts differ" in report
    assert "question 1: A '3' | B '4'" in report
    assert "base: reward A 0.25 | B 0.25; 0 of 2 output texts differ" in report


def test_the_environment_and_the_commits_are_shown():
    other = make_record(**{"environment.gpu_name": "GTX 1660 SUPER", "code.git_dirty": True})

    report, _ = load_script().compare(make_record(), other)

    assert "GTX 1660 SUPER" in report and "dirty True" in report


@pytest.mark.skipif(not EVIDENCE.exists(), reason="evidence folder not found")
def test_the_two_processes_of_the_real_5070ti_evidence_agree():
    first, second = (EVIDENCE / "5070ti.json"), (EVIDENCE / "5070ti_process2.json")

    completed = subprocess.run([sys.executable, str(SCRIPT), str(first), str(second)], capture_output=True, text=True)

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "0 of 16 output texts differ" in completed.stdout


def test_unusable_input_gives_exit_code_2(tmp_path):
    broken = tmp_path / "broken.json"
    broken.write_text("{}", encoding="utf-8")
    good = tmp_path / "good.json"
    good.write_text(json.dumps(make_record()), encoding="utf-8")

    for arguments in ([str(broken), str(good)], [str(tmp_path / "missing.json"), str(good)]):
        completed = subprocess.run([sys.executable, str(SCRIPT), *arguments], capture_output=True, text=True)
        assert completed.returncode == 2
        assert "unusable input" in completed.stderr


def test_a_different_library_version_alone_does_not_make_the_generation_config_different():
    # transformers 5.17 adds keys whose value is None and stores its own version: the settings are the same.
    newer = make_record(**{"model.generation_config_sha256": "x" * 64})
    newer["model"]["generation_config"].update({"use_mtp": None, "max_cache_len": None, "transformers_version": "5.17.0"})

    report, ok = load_script().compare(make_record(), newer)

    assert ok is True
    assert "raw generation config sha256 differs" in report
    assert "EQUAL     generation config (set values, no library version)" in report


def test_the_set_values_of_the_generation_config_decide_not_their_order_or_the_nones():
    reordered = make_record()
    reordered["model"]["generation_config"] = dict(reversed(list(reordered["model"]["generation_config"].items())))

    assert load_script().compare(make_record(), reordered)[1] is True


def test_the_recipe_hash_is_compared_and_a_record_of_format_2_uses_its_own():
    script = load_script()
    a = make_record()
    b = make_record()
    b["recipe_hash"] = "f" * 64          # a format-2 record carries the hash of the recipe it was run with

    report, ok = script.compare(a, b)

    assert ok is False and "DIFFERENT recipe hash (manifest v1)" in report
    assert script.recipe_hash_of(make_record()) == script.recipe_hash_of(make_record())   # rebuilt from the fields


def test_a_record_that_is_not_a_valid_recipe_is_reported_not_a_crash():
    broken = make_record(**{"runs.0.engine_version": "some_other_engine"})

    report, ok = load_script().compare(make_record(), broken)

    assert ok is False and "no valid recipe" in report
