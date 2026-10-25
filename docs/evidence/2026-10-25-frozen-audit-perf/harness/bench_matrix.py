"""One portable decode-throughput job: one model, one engine, fixed workload.

Designed to run unchanged on the local 5070 Ti and on the two remote 3060 WSL hosts. It imports only the
runtime source tree plus torch/transformers, writes one JSON object, and never touches shared caches: model
directories are passed explicitly and loaded with ``local_files_only``.

Workload matches the recorded vLLM receipt: eight fixed prompts, greedy, 32 new tokens, context 512, no
prefix cache, batches 1/8/32 with prompts repeated. One warmup per batch size, then ``--repeats`` timed runs.
"""

import argparse
import hashlib
import json
import os
import platform
import socket
import statistics
import time
from pathlib import Path

import torch
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
    "A train travels 60 kilometres per hour for 2.5 hours, then 80 kilometres per hour for 1.5 hours. "
    "Explain how far it travels in total, showing each step of the calculation, and finish with the total "
    "distance in kilometres as a single integer on the last line. Be careful with the multiplication and the "
    "addition, and do not skip any intermediate result. The answer is",
    "List three prime numbers greater than 50:",
    "def fibonacci(n):\n    ",
)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--engine", choices=("frozen", "b22", "fp16"), required=True)
    parser.add_argument("--model-path", type=Path, required=True)
    parser.add_argument("--label", default=None)
    parser.add_argument("--batch-sizes", type=int, nargs="+", default=[1, 8, 32])
    parser.add_argument("--max-new-tokens", type=int, default=32)
    parser.add_argument("--max-context", type=int, default=512)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--rank", type=int, default=8)
    parser.add_argument("--alpha", type=float, default=16.0)
    parser.add_argument("--seed", type=int, default=1234)
    parser.add_argument("--no-lora", action="store_true")
    parser.add_argument("--nonzero-adapter", action="store_true")
    parser.add_argument("--frozen-head", action="store_true")
    parser.add_argument("--decode-target", type=int, default=8)
    parser.add_argument("--json-out", type=Path, default=None)
    args = parser.parse_args()
    assert os.environ.get("HETEROES_GPU_ACCEPTANCE") == "1"
    assert torch.cuda.is_available()

    label = args.label or f"{args.model_path.name}-{args.engine}"
    files = file_manifest(args.model_path)
    tokenizer = AutoTokenizer.from_pretrained(args.model_path, local_files_only=True, trust_remote_code=False)
    prompts = [tokenizer(text)["input_ids"] for text in PROMPTS]
    header = {
        "kind": "header",
        "label": label,
        "engine": args.engine,
        "host": socket.gethostname(),
        "platform": platform.platform(),
        "gpu": torch.cuda.get_device_name(0),
        "torch": torch.__version__,
        "cuda": torch.version.cuda,
        "modelPath": str(args.model_path),
        "promptTokens": [len(prompt) for prompt in prompts],
        "promptDigest": hashlib.sha256(repr(prompts).encode()).hexdigest(),
        "workload": {
            "prompts": len(PROMPTS),
            "maxNewTokens": args.max_new_tokens,
            "maxContext": args.max_context,
            "greedy": True,
            "prefixCache": False,
            "repeats": args.repeats,
            "nonzeroAdapter": args.nonzero_adapter,
        },
    }
    print(json.dumps(header), flush=True)

    started = time.perf_counter()
    model, _ = load(args.model_path, files, "cuda")
    load_seconds = time.perf_counter() - started

    engine_seconds = 0.0
    if args.engine == "frozen":
        started = time.perf_counter()
        freeze_projections(model, rank=args.rank, alpha=args.alpha, seed=args.seed)
        if args.nonzero_adapter:
            # The constructor follows PEFT and zeroes B, so the adapter delta is exactly zero. Fill B
            # deterministically to exercise the strict add path in timed decode. This is a throughput probe,
            # not an ES perturbation and not a quality evaluation.
            generator = torch.Generator().manual_seed(args.seed)
            with torch.no_grad():
                for _, module in frozen_modules(model):
                    weight = torch.empty(module.lora_B[module.adapter_name].weight.shape, dtype=torch.float32)
                    weight.normal_(0.0, 0.02, generator=generator)
                    module.lora_B[module.adapter_name].weight.copy_(weight)
        if args.no_lora:
            for _, module in frozen_modules(model):
                module.lora_delta = lambda value, module=module: torch.zeros(
                    (*value.shape[:-1], module.out_features), dtype=torch.float32, device=value.device
                )
        if args.frozen_head:
            freeze_tied_head(model)
        torch.cuda.synchronize()
        engine_seconds = time.perf_counter() - started
        engine = FrozenInt8DecoderGraph(
            model,
            max_context=args.max_context,
            max_graph_bytes=4 * 1024**3,
            max_partial_bytes=64 * 1024**2,
            decode_target_ctas_per_sm=args.decode_target,
        )
    elif args.engine == "b22":
        engine = IntegerDecoderGraph(
            model,
            magnitude_bits=22,
            max_context=args.max_context,
            max_graph_bytes=4 * 1024**3,
            max_partial_bytes=64 * 1024**2,
        )
    else:
        from heteroes.eval.fp16_decoder import Fp16DecoderGraph

        engine = Fp16DecoderGraph(model, max_context=args.max_context, max_graph_bytes=4 * 1024**3)

    identity = {
        "kind": "identity",
        "label": label,
        "backend": engine.identity["backend"],
        "fingerprint": engine.fingerprint,
        "loadSeconds": load_seconds,
        "prepareSeconds": engine_seconds,
        "device": torch.cuda.get_device_name(0),
    }
    print(json.dumps(identity), flush=True)

    pad = tokenizer.pad_token_id if tokenizer.pad_token_id is not None else 0
    torch.cuda.reset_peak_memory_stats()

    @torch.inference_mode()
    def run(rows):
        width = max(map(len, rows))
        ids = torch.full((len(rows), width), pad, dtype=torch.long, device="cuda")
        mask = torch.zeros_like(ids)
        for index, row in enumerate(rows):
            ids[index, -len(row) :] = torch.tensor(row, dtype=torch.long, device="cuda")
            mask[index, -len(row) :] = 1
        output = engine.generate(
            ids,
            attention_mask=mask,
            do_sample=False,
            max_new_tokens=args.max_new_tokens,
            eos_token_id=[],
            pad_token_id=pad,
            repetition_penalty=1.0,
            use_cache=True,
        )
        return output[:, width:].tolist()

    rows_out = []
    for size in args.batch_sizes:
        rows = [prompts[index % len(prompts)] for index in range(size)]
        run(rows)
        durations, outputs = [], []
        for _ in range(args.repeats):
            torch.cuda.synchronize()
            started = time.perf_counter()
            output = run(rows)
            torch.cuda.synchronize()
            durations.append(time.perf_counter() - started)
            outputs.append(output)
        median = statistics.median(durations)
        row = {
            "kind": "result",
            "label": label,
            "engine": args.engine,
            "device": torch.cuda.get_device_name(0),
            "batch": size,
            "seconds": durations,
            "medianSeconds": median,
            "millisecondsPerStep": 1000.0 * median / args.max_new_tokens,
            "tokensPerSecond": size * args.max_new_tokens / median,
            "equal": all(item == outputs[0] for item in outputs),
            "sample": outputs[0][0][:8],
            "peakMemoryBytes": torch.cuda.max_memory_allocated(),
        }
        rows_out.append(row)
        print(json.dumps(row), flush=True)

    if args.json_out is not None:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(
            json.dumps({"header": header, "identity": identity, "results": rows_out}, indent=2) + "\n"
        )


if __name__ == "__main__":
    main()
