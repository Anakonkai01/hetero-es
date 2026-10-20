"""Managed views expose observed usage without rewriting numerical tables."""

from heteroes.product.files import write_json
from heteroes.product.run_supervisor import RunSupervisor
from test_v3_product import product_assets, product_config, run_product


class Projection(RunSupervisor):
    def launch(self, root):
        raise AssertionError("projection must not launch work")

    def remote(self, worker, request):
        raise AssertionError("projection must not send commands")

    def start_worker(self, root, worker, recovery):
        raise AssertionError("projection must not start workers")


def test_managed_projection_keeps_candidate_generation_and_total_usage(product_assets, tmp_path):
    supervisor = Projection({"stateDirectory": str(tmp_path / "runs"), "workers": []}, "fixture")
    run_id = "a" * 32
    root = supervisor.directory(run_id)
    root.mkdir()
    run_product(product_config(product_assets, root), root)
    write_json(root / "state.json", {"status": "COMPLETED"})
    projected = supervisor.snapshot(run_id)
    summary = projected["usageSummary"]
    assert summary["generatedTokens"] > 0 and summary["gpuSeconds"] == 0 and not summary["partial"]
    assert summary["generatedTokens"] == sum(g["usage"]["generatedTokens"] for g in projected["generations"])
    assert summary["generatedTokens"] == sum(sum(c["usage"]["generatedTokens"]) for c in projected["candidates"])
    assert all(c["usage"]["device"] == "cpu" for c in projected["candidates"])
