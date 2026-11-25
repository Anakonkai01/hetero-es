#!/usr/bin/env python3
"""
Trained-model parity of the strict B22 decoder: parent, canonical antithetic pair (seed 7001, sigma 1e-3, noise v2) and
exact restore, with the tile and streamed projection schedules, compared with the golden hashes.

The golden hashes (acceptance/golden/strict-b22.json) are the sealed receipts of runtime 0eb86cb9, equal on the 5070 Ti,
the 3060 under WSL2 and (Qwen) native Windows. A pass means: on this host and source, every state gives the same weights
hash, prefill logits hash, generated token hash and rewards; restore is exact; for Qwen the captured decode with real EOS
gives the golden tokens. Finite evidence only: no quality, learning, managed lifecycle or hardware qualification.

    HETEROES_GPU_ACCEPTANCE=1 PYTHONPATH=runtime/src:runtime/scripts python acceptance/probes/strict_parity.py --gpu \\
        --model qwen --models <dir with qwen/smol/tiny> --out receipt.json

Llama 3.2 (llama3 RoPE, added 2026-11) has its own golden file and chat workload (golden/strict-b22-llama32.json,
golden/workload-chat-llama32.json). `--record` runs a model that has no golden yet and writes the hashes this host
produced (status "recorded", tile and stream schedules must agree); golden/make_llama_golden.py turns that receipt into
the golden file, which another GPU then has to reproduce with the ordinary comparison run.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import time

HERE = Path(__file__).resolve().parent
p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
p.add_argument("--model", required=True, choices=("qwen", "smol", "tiny", "llama32"))
p.add_argument("--models", type=Path, required=True)
p.add_argument("--out", type=Path, required=True)
p.add_argument(
    "--golden", type=Path, help="default: golden/strict-b22.json (golden/strict-b22-llama32.json for llama32)"
)
p.add_argument("--chat-workload", type=Path, help="default: the golden's chatWorkload file (workload-chat-01.json)")
p.add_argument("--record", action="store_true", help="no comparison: write this host's hashes for a new golden")
p.add_argument("--gpu", action="store_true")
a = p.parse_args()
GOLDEN_DIR = HERE.parent / "golden"
if a.golden is None:
    a.golden = GOLDEN_DIR / ("strict-b22-llama32.json" if a.model == "llama32" else "strict-b22.json")
if not a.gpu or os.environ.get("HETEROES_GPU_ACCEPTANCE") != "1" or a.out.exists():
    p.error("GPU opt-in (--gpu and HETEROES_GPU_ACCEPTANCE=1) and a fresh --out are required")

import torch  # noqa: E402
import transformers  # noqa: E402

from heteroes.es.perturb import perturb_model_  # noqa: E402
from heteroes.es.snapshot import restore_from_snapshot_, take_snapshot  # noqa: E402
from heteroes.eval.candidate import model_weights_sha256  # noqa: E402
from heteroes.strict.integer_decoder import IntegerDecoderGraph  # noqa: E402
from heteroes.eval.workload import extract_integer  # noqa: E402
from heteroes.model.schema import build_parameter_schema  # noqa: E402
from heteroes.noise.contracts import ENGINE_V2  # noqa: E402
from heteroes.v3.model import file_manifest, load  # noqa: E402
from probe_strict_backend import EXPECTED, PROMPTS  # noqa: E402


def sha(value):
    return hashlib.sha256(value).hexdigest()


def digest(tensor):
    return sha(tensor.detach().cpu().contiguous().numpy().tobytes())


def left_padded(rows):
    width = max(len(r) for r in rows)
    ids = torch.zeros((len(rows), width), dtype=torch.long, device="cuda")
    mask = torch.zeros_like(ids)
    for i, row in enumerate(rows):
        ids[i, -len(row) :] = torch.tensor(row, device="cuda")
        mask[i, -len(row) :] = 1
    return ids, mask


if a.record:
    golden = {"chatWorkload": a.chat_workload.name if a.chat_workload else "workload-chat-llama32.json"}
else:
    golden = json.loads(a.golden.read_text())["models"][a.model]
if a.chat_workload is None:
    a.chat_workload = GOLDEN_DIR / golden.get("chatWorkload", "workload-chat-01.json")
report = {
    "status": "running",
    "model": a.model,
    "hardwareQualified": False,
    "probeSha256": sha(Path(__file__).read_bytes()),
    "goldenSha256": None if a.record else sha(a.golden.read_bytes()),
    "recorded": a.record,
    "environment": {
        "python": platform.python_version(),
        "torch": torch.__version__,
        "transformers": transformers.__version__,
        "platform": platform.platform(),
        "gpu": torch.cuda.get_device_name(),
        "computeCapability": list(torch.cuda.get_device_capability()),
    },
    "cases": [],
    "mismatches": [],
}
started = time.perf_counter()
try:
    files = file_manifest(a.models / a.model)
    model, tok = load(a.models / a.model, files, "cuda")
    schema = build_parameter_schema(model)
    snapshot = take_snapshot(model, schema)
    parent = model_weights_sha256(model, schema)
    report.update(modelFiles=files, parentSha256=parent, schemaHash=schema.hash)
    for key in ("modelFiles", "parentSha256", "schemaHash"):
        if not a.record and report[key] != golden[key]:
            raise ValueError(f"{key} differs from the golden experiment: wrong model files")
    engines = {
        name: IntegerDecoderGraph(
            model, magnitude_bits=22, max_context=512, max_graph_bytes=4 * 1024**3, mma_schedule=name
        )
        for name in ("tile", "stream")
    }
    report["kernelIdentity"] = engines["stream"].kernels.identity()
    prompts = [tok(t, return_tensors="pt")["input_ids"].cuda() for t in PROMPTS]
    workloads = [("short8", *left_padded([x[0].tolist() for x in prompts]), 32, EXPECTED)]
    if a.record:
        report["chatWorkload"] = a.chat_workload.name
        report["chatWorkloadSha256"] = golden["chatWorkloadSha256"] = sha(a.chat_workload.read_bytes())
    if "chatWorkloadSha256" in golden:
        if sha(a.chat_workload.read_bytes()) != golden["chatWorkloadSha256"]:
            raise ValueError("chat workload differs from the golden experiment")
        rows = json.loads(a.chat_workload.read_text())["models"][a.model]["rows"][:32]
        workloads.append(("chat32x128", *left_padded([r["tokenIds"] for r in rows]), 128, [None] * len(rows)))
    for state, seed, sigma in (
        ("parent", None, 0),
        ("plus", 7001, 1e-3),
        ("minus", 7001, -1e-3),
        ("restored", None, 0),
    ):
        case = {"state": state, "results": {}}
        report["cases"].append(case)
        try:
            if seed is not None:
                perturb_model_(model, schema, seed, sigma, engine=ENGINE_V2)
            case["weightsSha256"] = model_weights_sha256(model, schema)
            for name, engine in engines.items():
                logits, caches = engine.forward_batch(prompts)
                del caches
                out = {"prefillLogitsSha256": digest(logits)}
                for label, ids, mask, n, expected in workloads:
                    tokens = engine.generate(
                        ids,
                        attention_mask=mask,
                        max_new_tokens=n,
                        eos_token_id=[],
                        pad_token_id=0,
                        repetition_penalty=1.0,
                    )[:, ids.shape[1] :].tolist()
                    texts = [tok.decode(r, skip_special_tokens=True) for r in tokens]
                    rewards = [
                        float(extract_integer(t) == e) if e is not None else None for t, e in zip(texts, expected)
                    ]
                    out[label] = {"tokensSha256": sha(json.dumps(tokens).encode()), "rewards": rewards}
                case["results"][name] = out
                engine.release_graph()
        finally:
            restore_from_snapshot_(model, schema, snapshot)
            case["restoreExact"] = model_weights_sha256(model, schema) == parent
        if not case["restoreExact"]:
            raise ValueError("restore is not exact")
    if a.record:
        # a new golden needs both projection schedules to agree, as the sealed receipts of runtime 0eb86cb9 did
        for case in report["cases"]:
            if case["results"]["tile"] != case["results"]["stream"]:
                report["mismatches"].append(f"{case['state']}: tile differs from stream")
        eos_ids = model.generation_config.eos_token_id
        golden["eos"] = {
            "eosTokenIds": sorted(eos_ids if isinstance(eos_ids, list) else [eos_ids]),
            "maxNewTokens": 512 - workloads[1][1].shape[1],  # the engines' context is 512 tokens
        }
    else:
        for now, expected in zip(report["cases"], golden["cases"], strict=True):
            for key in ("state", "weightsSha256", "results"):
                if now[key] != expected[key]:
                    report["mismatches"].append(f"{now['state']}: {key}")
    if "eos" in golden:
        # real EOS on the parent: the captured decode with its one-step-ahead queue must give the golden tokens
        eos = golden["eos"]
        ids, mask = workloads[1][1:3]
        tokens = (
            engines["stream"]
            .generate(
                ids,
                attention_mask=mask,
                max_new_tokens=eos["maxNewTokens"],
                eos_token_id=eos["eosTokenIds"],
                pad_token_id=0,
                repetition_penalty=1.0,
            )[:, ids.shape[1] :]
            .tolist()
        )
        report["eos"] = {"tokensSha256": sha(json.dumps(tokens).encode())}
        if a.record:
            pad = 0  # rows that stopped early end in padding
            report["eos"].update(
                eosTokenIds=eos["eosTokenIds"],
                maxNewTokens=eos["maxNewTokens"],
                rowsEndingEarly=sum(
                    1 for r in tokens if r and r[-1] == pad and any(t in eos["eosTokenIds"] for t in r)
                ),
            )
        elif report["eos"]["tokensSha256"] != eos["tokensSha256"]:
            report["mismatches"].append("eos: tokensSha256")
    report["status"] = ("recorded" if a.record else "ok") if not report["mismatches"] else "mismatch"
except Exception as error:
    report.update(status="error", errorType=type(error).__name__, error=str(error)[:2000])
report["wallSeconds"] = time.perf_counter() - started
with a.out.open("x") as f:
    json.dump(report, f, indent=1)
    f.write("\n")
print(json.dumps({k: report.get(k) for k in ("status", "model", "mismatches", "error", "wallSeconds")}))
if report["status"] == "ok":
    print("PARITY OK")
if report["status"] == "recorded":
    print("RECORDED")
raise SystemExit(int(report["status"] not in ("ok", "recorded")))
