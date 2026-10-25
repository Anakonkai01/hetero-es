"""CPU checks for the common-workload comparison; no inference library or GPU is needed."""

import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "benchmark_inference.py"


def script():
    spec = importlib.util.spec_from_file_location("benchmark_inference", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("options", [[], ["--gpu", "--repeats", "0"], ["--gpu", "--batch-sizes", "0"]])
def test_benchmark_guards_before_inference_imports(tmp_path, monkeypatch, options):
    module = script()
    monkeypatch.setenv("HETEROES_GPU_ACCEPTANCE", "1")
    monkeypatch.setattr(module, "load_engine", lambda *args: pytest.fail("guard must run first"))
    with pytest.raises(SystemExit):
        module.main(["--engine", "strict", "--model-path", str(tmp_path), "--out", str(tmp_path / "r.json"), *options])


def test_measurement_warms_up_counts_exact_output_and_keeps_each_repeat(monkeypatch):
    module = script()
    times = iter([10.0, 12.0, 20.0, 24.0])
    monkeypatch.setattr(module.time, "perf_counter", lambda: next(times))
    calls = []

    def run(prompts):
        calls.append(prompts)
        return [[p[0], 9] for p in prompts]

    result = module.measure(run, [[1], [2, 3], [1]], 2, 2, lambda: None)
    assert len(calls) == 3  # warmup is excluded
    assert result["generatedTokensPerRepeat"] == 6
    assert result["seconds"] == [2.0, 4.0]
    assert result["medianSeconds"] == 3.0 and result["tokensPerSecondTotal"] == 2.0
    assert result["tokens"] == [[1, 9], [2, 9], [1, 9]] and result["repeatTokensEqual"] is True


@pytest.mark.parametrize("bad", [[], [[1, 2]], [[1], [2]], [[1, 2, 3], [4, 5]], [[True, 2], [1, 2]]])
def test_measurement_refuses_missing_rows_short_outputs_or_invalid_tokens(bad):
    with pytest.raises(ValueError, match="output"):
        script().measure(lambda _: bad, [[1], [2]], 2, 1, lambda: None)


def test_measurement_detects_a_changed_repeat(monkeypatch):
    module = script()
    times = iter(range(4))
    monkeypatch.setattr(module.time, "perf_counter", lambda: next(times))
    outputs = iter([[[1]], [[1]], [[2]]])
    assert module.measure(lambda _: next(outputs), [[7]], 1, 2, lambda: None)["repeatTokensEqual"] is False


@pytest.mark.parametrize("precision", ["13", "23", "0"])
def test_integer_precision_guard_precedes_model_loading(tmp_path, monkeypatch, precision):
    module = script()
    monkeypatch.setenv("HETEROES_GPU_ACCEPTANCE", "1")
    monkeypatch.setattr(module, "load_engine", lambda *args: pytest.fail("precision guard must run first"))
    with pytest.raises(SystemExit):
        module.main(
            [
                "--engine",
                "strict-integer",
                "--integer-bits",
                precision,
                "--gpu",
                "--model-path",
                str(tmp_path),
                "--out",
                str(tmp_path / "r.json"),
            ]
        )
