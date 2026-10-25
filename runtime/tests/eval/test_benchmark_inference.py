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


@pytest.mark.parametrize(
    "options",
    [
        [],
        ["--gpu", "--repeats", "0"],
        ["--gpu", "--batch-sizes", "0"],
        ["--gpu", "--decode-ctas-per-sm", "-1"],
        ["--gpu", "--decode-ctas-per-sm", "65"],
    ],
)
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


def test_existing_output_is_rejected_before_model_loading(tmp_path, monkeypatch):
    module = script()
    destination = tmp_path / "existing.json"
    destination.write_text("original evidence")
    monkeypatch.setenv("HETEROES_GPU_ACCEPTANCE", "1")
    monkeypatch.setattr(module, "load_engine", lambda *args: pytest.fail("existing evidence guard must run first"))
    with pytest.raises(SystemExit):
        module.main(["--engine", "hf-shadow", "--gpu", "--model-path", str(tmp_path), "--out", str(destination)])
    assert destination.read_text() == "original evidence"


def test_shadow_refresh_is_inside_each_timed_observation_and_warmup(monkeypatch):
    module = script()
    times = iter([10.0, 10.5, 12.0, 20.0, 21.0, 24.0])
    monkeypatch.setattr(module.time, "perf_counter", lambda: next(times))
    calls = []

    def refresh():
        calls.append("refresh")

    def run(rows):
        calls.append("generate")
        return [[7, 8]]

    result = module.measure(run, [[1]], 2, 2, lambda: None, before_run=refresh)
    assert calls == ["refresh", "generate"] * 3
    assert result["seconds"] == [2.0, 4.0]
    assert result["refreshSeconds"] == [0.5, 1.0]
    assert result["decodeSeconds"] == [1.5, 3.0]
    assert result["tokensPerSecondTotal"] == 2 / 3
    assert result["decodeOnlyTokensPerSecondTotal"] == 2 / 2.25


def test_hf_shadow_keeps_live_fp16_and_refreshes_exact_widened_weights():
    import torch

    module = script()
    live = torch.nn.Linear(3, 2, bias=False).half()
    shadow = module.make_shadow(live)
    assert shadow.model is not live
    assert live.weight.dtype == torch.float16 and shadow.model.weight.dtype == torch.float32
    with torch.no_grad():
        live.weight.fill_(0.125)
    shadow.refresh()
    assert torch.equal(shadow.model.weight, torch.full((2, 3), 0.125, dtype=torch.float32))
    assert shadow.model.weight.data_ptr() != live.weight.data_ptr()


def test_decoder_run_preserves_order_and_padding_when_chunking():
    import torch

    module = script()
    seen = []

    class Engine:
        def generate(self, ids, **kwargs):
            seen.append((ids.tolist(), kwargs["attention_mask"].tolist()))
            assert kwargs["eos_token_id"] == [] and kwargs["do_sample"] is False
            assert kwargs["repetition_penalty"] == 1.0 and kwargs["use_cache"] is True
            return torch.cat((ids, ids[:, -1:].repeat(1, kwargs["max_new_tokens"])), dim=1)

    run = module.decoder_run(Engine(), pad=0, tokens=2, device="cpu", chunk=2)
    assert run([[1], [2, 3], [4]]) == [[1, 1], [3, 3], [4, 4]]
    assert seen == [([[0, 1], [2, 3]], [[0, 1], [1, 1]]), ([[4]], [[1]])]


@pytest.mark.parametrize(
    "engine,options",
    [
        ("hf-shadow", ["--frozen-head"]),
        ("strict-integer", ["--hf-chunk", "16"]),
        ("strict-frozen", ["--lora-rank", "33"]),
        ("strict-frozen", ["--lora-alpha", "nan"]),
        ("hf-shadow", ["--hf-chunk", "-1"]),
    ],
)
def test_comparison_options_fail_before_loading(tmp_path, monkeypatch, engine, options):
    module = script()
    monkeypatch.setenv("HETEROES_GPU_ACCEPTANCE", "1")
    monkeypatch.setattr(module, "load_engine", lambda *args: pytest.fail("option guard must run first"))
    with pytest.raises(SystemExit):
        module.main(
            ["--engine", engine, "--gpu", "--model-path", str(tmp_path), "--out", str(tmp_path / "r.json"), *options]
        )
