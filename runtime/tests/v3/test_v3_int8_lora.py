"""
M6: `strict_int8_lora_v1`, a Recipe v3 decoder over a frozen int8 base (pinned per-row int8 projections, no FP16 copy of
them left) with FP16 LoRA adapters as the only trainable parameters. The base is quantized from the pinned FP16 files,
its hash is part of the weight space, and every machine that loads the recipe recomputes and checks it.
"""

import json
import os

import pytest
import torch

from heteroes.catalog import STRICT_B22_DECODER, STRICT_INT8_LORA_DECODER
from heteroes.v3.local import run_local
from heteroes.v3.model import file_manifest, freeze_base_, load, trainable_schema
from heteroes.v3.options import STRICT_CHUNKS, exact_chunks
from test_v3_local import assets, check_run, config_for  # noqa: F401 - fixtures

SPACE = {"kind": "lora", "rank": 2, "alpha": 4, "targetModules": ["q_proj", "v_proj", "down_proj"]}


def int8_config(assets, **changes):  # noqa: F811
    return config_for(
        assets, **{"weightSpace": dict(SPACE), "decoder": STRICT_INT8_LORA_DECODER, "evalDtype": "float16"} | changes
    )


def test_the_int8_decoder_is_a_new_strict_value_with_the_strict_chunks():
    from heteroes.catalog import STRICT_DECODERS, V3_DECODE_ENGINES

    assert STRICT_INT8_LORA_DECODER == "strict_int8_lora_v1"
    assert STRICT_DECODERS == (STRICT_B22_DECODER, STRICT_INT8_LORA_DECODER)
    assert STRICT_INT8_LORA_DECODER in V3_DECODE_ENGINES
    assert exact_chunks("float16", STRICT_INT8_LORA_DECODER) == STRICT_CHUNKS


def test_freezing_replaces_the_targets_and_leaves_no_fp16_copy(assets):  # noqa: F811
    model, _ = load(assets / "model", file_manifest(assets / "model"))
    names = [n for n, m in model.named_modules() if isinstance(m, torch.nn.Linear) and n.endswith(".q_proj")]
    first = freeze_base_(model, SPACE)
    assert first == freeze_base_(load(assets / "model", file_manifest(assets / "model"))[0], SPACE)  # deterministic
    for name in names:
        module = model.get_submodule(name)
        assert getattr(module, "is_frozen_int8_linear", False) and module.weight_q.dtype == torch.int8
        assert not any(p.dtype == torch.float16 and "lora_" not in n for n, p in module.named_parameters())
    assert all("lora_" in n for n, p in model.named_parameters() if any(t in n for t in SPACE["targetModules"]))


def test_a_recipe_pins_the_frozen_base_and_a_worker_checks_it(assets, tmp_path):  # noqa: F811
    from heteroes.v3.local import prepare

    ready = prepare(int8_config(assets), tmp_path / "run")
    recipe = json.loads((tmp_path / "run" / "recipe.json").read_text())
    space = recipe["weightSpace"]
    assert set(space) == {*SPACE, "initialAdapterSha256", "frozenBaseSha256"}
    assert (
        recipe["evaluation"]["decoder"] == STRICT_INT8_LORA_DECODER and recipe["evaluation"]["evalDtype"] == "float16"
    )
    assert all(".lora_" in e.canonical_name for e in ready["schema"].entries)
    worker, _, schema = ready["worker_model"]()
    assert schema.hash == recipe["schemaHash"] and any("weight_q" in name for name, _ in worker.named_buffers())
    fresh, _ = load(assets / "model", file_manifest(assets / "model"))
    with pytest.raises(ValueError, match="frozen int8 base"):
        trainable_schema(fresh, {**space, "frozenBaseSha256": "0" * 64}, tmp_path / "run" / "initial-adapter.bin")


@pytest.mark.parametrize(
    "changes, message",
    [
        ({"evalDtype": "float32"}, "FP16"),
        ({"weightSpace": {"kind": "subset", "include": ["q_proj"]}}, "LoRA"),
        ({"weightSpace": {**SPACE, "rank": 33}}, "rank"),
    ],
)
def test_the_int8_decoder_needs_fp16_lora_and_a_small_rank(assets, tmp_path, changes, message):  # noqa: F811
    from heteroes.v3.local import prepare

    with pytest.raises(ValueError, match=message):
        prepare(int8_config(assets, **changes), tmp_path / "run")


def test_a_plain_lora_recipe_keeps_its_fields(assets, tmp_path):  # noqa: F811
    from heteroes.v3.local import prepare

    prepare(config_for(assets, weightSpace=dict(SPACE)), tmp_path / "run")
    space = json.loads((tmp_path / "run" / "recipe.json").read_text())["weightSpace"]
    assert set(space) == {*SPACE, "initialAdapterSha256"}  # earlier LoRA documents and hashes are unchanged


def test_documents_tie_the_frozen_base_to_the_int8_decoder(assets, tmp_path):  # noqa: F811
    from heteroes.v3.documents import validate_recipe
    from heteroes.v3.local import prepare

    prepare(int8_config(assets), tmp_path / "run")
    recipe = json.loads((tmp_path / "run" / "recipe.json").read_text())
    validate_recipe(recipe)
    without = {**recipe, "weightSpace": {k: v for k, v in recipe["weightSpace"].items() if k != "frozenBaseSha256"}}
    with pytest.raises(ValueError, match="frozen"):
        validate_recipe(without)
    other = {**recipe, "evaluation": {**recipe["evaluation"], "decoder": STRICT_B22_DECODER}}
    with pytest.raises(ValueError, match="frozen"):
        validate_recipe(other)


def test_the_lab_does_not_offer_the_int8_decoder_yet():
    from heteroes.v3.lab_cli import managed_configuration

    spec = {
        "model": {"id": "m"},
        "data": {"batchSize": 4},
        "sigma": {"initial": 0.1},
        "generations": 1,
        "population": 2,
        "alpha": 0.1,
        "scorer": {"name": "last-integer"},
        "decoder": STRICT_INT8_LORA_DECODER,
        "evalDtype": "float16",
        "weightSpace": dict(SPACE),
    }
    with pytest.raises(ValueError, match="standalone"):
        managed_configuration(spec, "c", ["w"], {"id": "m"}, {"datasetId": "d"})


gpu = pytest.mark.skipif(
    os.environ.get("HETEROES_GPU_ACCEPTANCE") != "1" or not torch.cuda.is_available(), reason="GPU opt-in"
)


@gpu
def test_an_int8_run_replays_on_the_cpu_and_keeps_no_fp16_targets_on_the_gpu(assets, tmp_path, monkeypatch):  # noqa: F811
    from heteroes.eval import strict_backend
    from heteroes.v3.local import prepare

    monkeypatch.delenv("HETEROES_GPU_ACCEPTANCE")  # the strict recipe is the opt-in
    config = int8_config(assets, evalChunk=4, population=4, generations=2, sigma={"initial": 0.5})
    # one worker: two captured strict engines in one process may not capture at the same time (cross-GPU audits are
    # the e2e probe's: acceptance/probes/strict_e2e.py --int8-lora)
    summaries = run_local(config, tmp_path / "run", device="cuda", workers=1, audit_rate=0)
    assert len(summaries) == 2
    assert any(s["changed"] for s in summaries)
    _, _, children = check_run(tmp_path / "run", assets)  # CPU replay of every published child
    assert children[-1] == summaries[-1]["child_sha256"]
    ready = prepare(config, tmp_path / "again", device="cuda")
    model = ready["model"]
    assert not any(
        p.device.type == "cuda" and p.dtype == torch.float16 and t in n and "lora_" not in n
        for n, p in model.named_parameters()
        for t in SPACE["targetModules"]
    )
    from heteroes.study.evaluation import generate_rows

    run = ready["run"]
    rows = list(ready["dataset"]["splits"]["validation"])[:4]
    first = generate_rows(model, ready["tokenizer"], rows, run.evaluation, 4)
    assert type(strict_backend.engine_for(model)).__name__ == "FrozenInt8DecoderGraph"
    assert generate_rows(model, ready["tokenizer"], rows, run.evaluation, 1) == first  # rows are independent


def test_the_int8_decoder_stops_at_the_first_audit_mismatch_and_refuses_export(tmp_path):
    from types import SimpleNamespace

    from heteroes.v3.audit_guard import strict_stop_for
    from heteroes.v3.tracker import Tracker

    assert strict_stop_for(SimpleNamespace(evaluation={"decoder": STRICT_INT8_LORA_DECODER}))
    tracker = object.__new__(Tracker)
    tracker.root, tracker.best = tmp_path, {"weightsSha256": "a" * 64}
    tracker.recipe = SimpleNamespace(recipe={"weightSpace": {**SPACE, "frozenBaseSha256": "b" * 64}})
    with pytest.raises(ValueError, match="frozen int8 base"):
        tracker.export()
