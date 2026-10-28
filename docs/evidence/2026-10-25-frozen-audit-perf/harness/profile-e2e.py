"""Profile one captured B32 generate and print the top CUDA kernels."""

import argparse
import os
from pathlib import Path

import torch
from torch.profiler import ProfilerActivity, profile
from transformers import AutoTokenizer

from heteroes.eval.frozen_int8_decoder import FrozenInt8DecoderGraph
from heteroes.eval.integer_decoder import IntegerDecoderGraph
from heteroes.model.frozen_int8 import freeze_projections, freeze_tied_head, frozen_modules
from heteroes.v3.model import file_manifest, load

PROMPTS = (
    "Return only the answer: 2 + 2 =",
    "Q: Tom has 3 apples and buys 5 more. How many apples does he have? Answer with a number.\nA:",
    "Write the next number in the sequence 2, 4, 8, 16,",
    "Natalia sold clips to 48 of her friends in April, and then she sold half as many clips to her friends in "
    "May. How many clips did Natalia sell altogether in April and May? Think step by step, then give the final "
    "number.",
    "Translate to French: The cat is sleeping on the warm windowsill.",
    "A train travels 60 kilometres per hour for 2.5 hours, then 80 kilometres per hour for 1.5 hours. Explain.",
    "List three prime numbers greater than 50:",
    "def fibonacci(n):\n    ",
)

parser = argparse.ArgumentParser()
parser.add_argument("--engine", choices=("frozen", "b22", "fp16"), required=True)
parser.add_argument("--model-path", type=Path, required=True)
parser.add_argument("--frozen-head", action="store_true")
parser.add_argument("--no-lora", action="store_true")
parser.add_argument("--batch", type=int, default=32)
args = parser.parse_args()
assert os.environ.get("HETEROES_GPU_ACCEPTANCE") == "1"

tokenizer = AutoTokenizer.from_pretrained(args.model_path, local_files_only=True, trust_remote_code=False)
prompts = [tokenizer(text)["input_ids"] for text in PROMPTS]
model, _ = load(args.model_path, file_manifest(args.model_path), "cuda")
if args.engine == "frozen":
    freeze_projections(model, rank=8, alpha=16.0, seed=1234)
    if args.no_lora:
        for _, module in frozen_modules(model):
            module.lora_delta = lambda value, module=module: torch.zeros((*value.shape[:-1], module.out_features), dtype=torch.float32, device=value.device)
    if args.frozen_head:
        freeze_tied_head(model)
    engine = FrozenInt8DecoderGraph(model, max_context=512, max_graph_bytes=4 * 1024**3, max_partial_bytes=64 * 1024**2)
elif args.engine == "b22":
    engine = IntegerDecoderGraph(
        model, magnitude_bits=22, max_context=512, max_graph_bytes=4 * 1024**3, max_partial_bytes=64 * 1024**2
    )
else:
    from heteroes.eval.fp16_decoder import Fp16DecoderGraph

    engine = Fp16DecoderGraph(model, max_context=512, max_graph_bytes=4 * 1024**3)

pad = tokenizer.pad_token_id or 0
rows = [prompts[i % len(prompts)] for i in range(args.batch)]
width = max(map(len, rows))
ids = torch.full((args.batch, width), pad, dtype=torch.long, device="cuda")
mask = torch.zeros_like(ids)
for i, row in enumerate(rows):
    ids[i, -len(row) :] = torch.tensor(row, dtype=torch.long, device="cuda")
    mask[i, -len(row) :] = 1


@torch.inference_mode()
def run():
    return engine.generate(
        ids,
        attention_mask=mask,
        do_sample=False,
        max_new_tokens=32,
        eos_token_id=[],
        pad_token_id=pad,
        repetition_penalty=1.0,
        use_cache=True,
    )


run()
torch.cuda.synchronize()
with profile(activities=[ProfilerActivity.CPU, ProfilerActivity.CUDA], record_shapes=False) as prof:
    run()
    torch.cuda.synchronize()
print(prof.key_averages().table(sort_by="self_cuda_time_total", row_limit=35))
