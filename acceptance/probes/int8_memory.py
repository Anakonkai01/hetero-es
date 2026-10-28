#!/usr/bin/env python3
"""
M6 memory per phase on this GPU: load the pinned FP16 model, freeze its LoRA targets to int8 (`freeze_base_`), then
evaluate one candidate (perturb, strict int8 decode, exact restore) through the executor. Prints a JSON receipt and
"INT8 MEMORY OK" when the frozen model holds less than the FP16 model and no FP16 copy of a frozen projection remains.

    HETEROES_GPU_ACCEPTANCE=1 PYTHONPATH=runtime/src python3 acceptance/probes/int8_memory.py --gpu --model <dir>
"""

import argparse
import json
from pathlib import Path
import sys

import torch

p = argparse.ArgumentParser()
p.add_argument("--gpu", action="store_true", required=True)
p.add_argument("--model", type=Path, required=True)
p.add_argument("--out", type=Path)
a = p.parse_args()

from heteroes.eval.candidate import model_weights_sha256  # noqa: E402
from heteroes.executor import CandidateExecutor  # noqa: E402
from heteroes.manifest import CandidateDescriptor  # noqa: E402
from heteroes.v3 import data as v3data  # noqa: E402
from heteroes.v3.local import prepare  # noqa: E402

TARGETS = ["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"]
mib = 2**20
rows = [{"question": f"What is {i} + {i + 7}?", "answer": 2 * i + 7} for i in range(40)]
out = Path(a.out or "/tmp") / "int8-memory-run"
out.mkdir(parents=True, exist_ok=True)
(out / "rows.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
config = {
    "model": {"path": str(a.model), "id": "Qwen/Qwen2.5-0.5B-Instruct"},
    "data": {"path": str(out / "rows.jsonl"), "promptField": "question", "batchSize": 16},
    "weightSpace": {"kind": "lora", "rank": 8, "alpha": 16, "targetModules": TARGETS},
    "sigma": {"initial": 0.02},
    "maxNewTokens": 32,
    "systemPrompt": "Answer with the number only.",
    "evalDtype": "float16",
    "decoder": "strict_int8_lora_v1",
    "evalChunk": 16,
    "population": 2,
    "generations": 1,
    "alpha": 0.001,
    "scorer": {"kind": "declarative", "name": "last-integer", "version": 1, "codeSha256": None, "config": {}},
}
torch.cuda.reset_peak_memory_stats()
base = torch.cuda.memory_allocated()
ready = prepare(config, out / "run", device="cuda")
model, run = ready["model"], ready["run"]
loaded = {
    "allocatedMiB": (torch.cuda.memory_allocated() - base) / mib,
    "peakMiB": torch.cuda.max_memory_allocated() / mib,
}
fp16 = sum(p.numel() * p.element_size() for p in model.parameters() if p.dtype == torch.float16)
frozen_fp16 = [n for n, p in model.named_parameters() if any(f".{t}." in n for t in TARGETS) and ".lora_" not in n]
torch.cuda.reset_peak_memory_stats()
executor = CandidateExecutor(model, ready["tokenizer"], ready["schema"], run, dataset=ready["dataset"], chunk=16)
executor.set_generation(0, run.context(ready["dataset"], 0))
parent = model_weights_sha256(model, ready["schema"])
reward = executor(CandidateDescriptor(run.hash, parent, "c", 0, 0, 17))
candidate = {"peakMiB": torch.cuda.max_memory_allocated() / mib, "allocatedMiB": torch.cuda.memory_allocated() / mib}
receipt = {
    "gpu": torch.cuda.get_device_name(),
    "fp16ParameterMiBAfterFreeze": fp16 / mib,
    "frozenProjectionFp16Parameters": frozen_fp16,
    "load": loaded,
    "candidate": candidate,
    "restoredExactly": model_weights_sha256(model, ready["schema"]) == parent,
    "frozenBaseSha256": run.recipe["weightSpace"]["frozenBaseSha256"],
    "reward": reward,
}
print(json.dumps(receipt, indent=1))
ok = not frozen_fp16 and receipt["restoredExactly"] and loaded["allocatedMiB"] < 942  # 942 MiB = the FP16 model
if a.out:
    (a.out / "int8-memory.json").write_text(json.dumps(receipt, indent=1) + "\n")
print("INT8 MEMORY OK" if ok else "INT8 MEMORY FAILED")
sys.exit(0 if ok else 1)
