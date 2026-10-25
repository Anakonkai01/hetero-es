#!/usr/bin/env python3
"""Compare strict, native HF and vLLM with identical token inputs and a fixed greedy output budget.

Run each engine in a separate process/environment, on the same GPU, with --gpu and HETEROES_GPU_ACCEPTANCE=1.
Uses local safetensors only. One warmup per batch size is excluded; synchronized host wall time includes
prefill, decode and engine overhead. EOS stopping and prefix reuse are disabled. This is an offline throughput
comparison, not a serving latency, quality, managed lifecycle or heterogeneous-equality qualification.
"""

import argparse
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import platform
import statistics
import time


def measure(run, prompts, tokens, repeats, synchronize, *, before_run=None):
    def checked():
        output = run(prompts)
        if len(output) != len(prompts) or any(
            len(row) != tokens or any(type(t) is not int or t < 0 for t in row) for row in output
        ):
            raise ValueError("Engine output must contain the requested integer tokens for every row")
        return output

    if before_run is not None:
        before_run()
    checked()  # untimed warmup
    durations, outputs, refresh_durations, decode_durations = [], [], [], []
    for _ in range(repeats):
        synchronize()
        start = time.perf_counter()
        refreshed = start
        if before_run is not None:
            before_run()
            synchronize()
            refreshed = time.perf_counter()
        output = checked()
        synchronize()
        end = time.perf_counter()
        durations.append(end - start)
        refresh_durations.append(refreshed - start)
        decode_durations.append(end - refreshed)
        outputs.append(output)
    median = statistics.median(durations)
    return {
        "sequences": len(prompts),
        "generatedTokensPerRepeat": len(prompts) * tokens,
        "seconds": durations,
        "refreshSeconds": refresh_durations,
        "decodeSeconds": decode_durations,
        "medianSeconds": median,
        "tokensPerSecondTotal": len(prompts) * tokens / median,
        "decodeOnlyTokensPerSecondTotal": len(prompts) * tokens / statistics.median(decode_durations),
        "repeatTokensEqual": all(output == outputs[0] for output in outputs),
        "tokens": outputs[0],
    }


def make_shadow(model):
    """Use the original evaluator, retaining live FP16 and its complete FP32 shadow."""
    from heteroes.eval.precision import EvalModel

    return EvalModel(model, "float32")


def decoder_run(engine, *, pad, tokens, device="cuda", chunk=0):
    import torch

    @torch.inference_mode()
    def run(rows):
        output_rows = []
        for offset in range(0, len(rows), chunk or len(rows)):
            group = rows[offset : offset + (chunk or len(rows))]
            width = max(map(len, group))
            ids = torch.full((len(group), width), pad, dtype=torch.long, device=device)
            mask = torch.zeros_like(ids)
            for i, row in enumerate(group):
                ids[i, -len(row) :] = torch.tensor(row, dtype=torch.long, device=device)
                mask[i, -len(row) :] = 1
            output = engine.generate(
                ids,
                attention_mask=mask,
                do_sample=False,
                max_new_tokens=tokens,
                eos_token_id=[],
                pad_token_id=pad,
                repetition_penalty=1.0,
                use_cache=True,
            )
            output_rows.extend(output[:, width:].tolist())
        return output_rows

    return run


def load_engine(args, report):
    import torch
    import transformers
    from transformers import AutoTokenizer

    from heteroes.v3.model import file_manifest, load

    files = file_manifest(args.model_path)
    report["modelFiles"] = files
    tokenizer = AutoTokenizer.from_pretrained(args.model_path, local_files_only=True, trust_remote_code=False)
    report["environment"].update(
        torch=torch.__version__,
        transformers=transformers.__version__,
        gpu=torch.cuda.get_device_name(0),
        computeCapability=list(torch.cuda.get_device_capability(0)),
        cuda=torch.version.cuda,
        matmulAllowTF32=torch.backends.cuda.matmul.allow_tf32,
    )
    spec = importlib.util.spec_from_file_location("strict_probe", Path(__file__).with_name("probe_strict_backend.py"))
    probe = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(probe)
    prompt_ids = [tokenizer(text)["input_ids"] for text in probe.PROMPTS]
    if max(map(len, prompt_ids)) + args.max_new_tokens > args.max_context:
        raise ValueError("Prompt/token budget exceeds the context limit")
    report["promptTokenIds"] = prompt_ids
    torch.cuda.reset_peak_memory_stats()
    if args.engine == "vllm":
        import vllm
        from vllm import LLM, SamplingParams

        report["environment"].update(
            vllm=vllm.__version__,
            batchInvariant=os.environ.get("VLLM_BATCH_INVARIANT", "0"),
            multiprocessing=os.environ.get("VLLM_ENABLE_V1_MULTIPROCESSING", "1"),
            enforceEager=args.enforce_eager,
        )
        root = Path(vllm.__file__).parent
        names = (
            "model_executor/layers/rotary_embedding/base.py",
            "model_executor/determinism/batch_invariant.py",
            "model_executor/determinism/batch_invariant_configs.py",
        )
        report["engineSources"] = {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in names}
        engine = LLM(
            model=str(args.model_path),
            dtype="float16",
            max_model_len=args.max_context,
            gpu_memory_utilization=args.memory_fraction,
            seed=0,
            enable_prefix_caching=False,
            enforce_eager=args.enforce_eager,
        )
        params = SamplingParams(
            temperature=0.0, max_tokens=args.max_new_tokens, ignore_eos=True, repetition_penalty=1.0
        )

        def run(rows):
            result = engine.generate([{"prompt_token_ids": ids} for ids in rows], params, use_tqdm=False)
            return [list(row.outputs[0].token_ids) for row in result]

    else:
        model, _ = load(args.model_path, files, "cuda")
        if args.engine in ("strict", "strict-packed", "strict-graph", "strict-integer"):
            from heteroes.eval.integer_decoder import IntegerDecoderGraph
            from heteroes.eval.strict_decoder import StrictDecoderCuda
            from heteroes.eval.strict_decoder_graph import StrictDecoderGraph
            from heteroes.eval.strict_decoder_packed import StrictDecoderPacked

            backend = {
                "strict": StrictDecoderCuda,
                "strict-packed": StrictDecoderPacked,
                "strict-graph": StrictDecoderGraph,
                "strict-integer": IntegerDecoderGraph,
            }[args.engine]
            options = (
                {"max_graph_bytes": args.graph_max_bytes} if args.engine in ("strict-graph", "strict-integer") else {}
            )
            if args.engine == "strict-integer":
                options["magnitude_bits"] = args.integer_bits
                options["decode_target_ctas_per_sm"] = getattr(args, "decode_ctas_per_sm", 8)
            engine = backend(model, max_context=args.max_context, **options)
            report["backendIdentity"] = engine.identity
        elif args.engine == "strict-frozen":
            from heteroes.eval.frozen_int8_decoder import FrozenInt8DecoderGraph
            from heteroes.model.frozen_int8 import freeze_projections, freeze_tied_head, frozen_modules

            report["frozenArtifacts"] = freeze_projections(
                model, rank=args.lora_rank, alpha=args.lora_alpha, seed=args.adapter_seed
            )
            if args.nonzero_adapter:
                generator = torch.Generator().manual_seed(args.adapter_seed)
                with torch.no_grad():
                    for _, module in frozen_modules(model):
                        weight = torch.empty(module.lora_B[module.adapter_name].weight.shape, dtype=torch.float32)
                        weight.normal_(0.0, 0.02, generator=generator)
                        module.lora_B[module.adapter_name].weight.copy_(weight)
            report["adapterTensorSha256"] = {
                name: hashlib.sha256(parameter.detach().cpu().contiguous().numpy().tobytes()).hexdigest()
                for name, parameter in model.named_parameters()
                if "lora_A" in name or "lora_B" in name
            }
            if args.frozen_head:
                report["frozenHeadArtifact"] = freeze_tied_head(model)
            engine = FrozenInt8DecoderGraph(
                model,
                max_context=args.max_context,
                max_graph_bytes=args.graph_max_bytes,
                max_partial_bytes=64 * 1024**2,
                decode_target_ctas_per_sm=args.decode_ctas_per_sm,
            )
            report["backendIdentity"] = engine.identity
        elif args.engine == "hf-shadow":
            evaluator = make_shadow(model)
            engine = evaluator.model
            report["environment"]["hfAttentionImplementation"] = engine.config._attn_implementation
            report["shadowStorage"] = {
                "liveParameterBytes": sum(p.numel() * p.element_size() for p in model.parameters()),
                "shadowParameterBytes": sum(p.numel() * p.element_size() for p in engine.parameters()),
                "liveDtypes": sorted({str(p.dtype) for p in model.parameters()}),
                "shadowDtypes": sorted({str(p.dtype) for p in engine.parameters()}),
                "refreshIncludedInTimedObservation": True,
            }
        else:
            engine = model
            report["environment"]["hfAttentionImplementation"] = model.config._attn_implementation
        pad = tokenizer.pad_token_id if tokenizer.pad_token_id is not None else 0

        run = decoder_run(engine, pad=pad, tokens=args.max_new_tokens, chunk=args.hf_chunk)
        if args.engine == "hf-shadow":
            # The bound refresh method keeps both full models alive throughout the job.
            run.before_run = evaluator.refresh

    return engine, prompt_ids, run


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--engine",
        choices=(
            "strict",
            "strict-packed",
            "strict-graph",
            "strict-integer",
            "strict-frozen",
            "hf",
            "hf-shadow",
            "vllm",
        ),
        required=True,
    )
    parser.add_argument(
        "--integer-bits",
        type=int,
        choices=(14, 22),
        default=22,
        help="strict-integer only: NEW row-scaled arithmetic, not FP32-tree equivalence",
    )
    parser.add_argument("--model-path", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--gpu", action="store_true")
    parser.add_argument(
        "--decode-ctas-per-sm",
        type=int,
        default=8,
        help="strict-integer decode only: occupancy target 0..64; 0 disables automatic split-K",
    )
    parser.add_argument("--batch-sizes", type=int, nargs="+", default=[1, 8, 32])
    parser.add_argument("--max-new-tokens", type=int, default=32)
    parser.add_argument("--max-context", type=int, default=512)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--memory-fraction", type=float, default=0.35)
    parser.add_argument("--graph-max-bytes", type=int, default=1024**3, help="strict-graph scratch admission budget")
    parser.add_argument("--enforce-eager", action="store_true", help="vLLM only: disable CUDA Graph replay")
    parser.add_argument("--hf-chunk", type=int, default=0, help="HF only: chunk size; 0 means the entire batch")
    parser.add_argument("--frozen-head", action="store_true", help="strict-frozen only: quantize a tied head sidecar")
    parser.add_argument(
        "--nonzero-adapter", action="store_true", help="strict-frozen only: fixed random throughput probe"
    )
    parser.add_argument("--lora-rank", type=int, default=8)
    parser.add_argument("--lora-alpha", type=float, default=16.0)
    parser.add_argument("--adapter-seed", type=int, default=1234)
    args = parser.parse_args(argv)
    if args.out.exists():
        parser.error("Evidence exists; choose a fresh --out")
    if not args.gpu or os.environ.get("HETEROES_GPU_ACCEPTANCE") != "1":
        parser.error("Requires --gpu and HETEROES_GPU_ACCEPTANCE=1")
    if (
        not 1 <= args.repeats <= 20
        or not 1 <= args.max_new_tokens <= 512
        or not 1 <= args.max_context <= 4096
        or any(not 1 <= size <= 128 for size in args.batch_sizes)
        or not 0 < args.memory_fraction < 0.9
        or not 1 <= args.graph_max_bytes <= 64 * 1024**3
        or not 0 <= args.decode_ctas_per_sm <= 64
        or not 0 <= args.hf_chunk <= 128
        or not 1 <= args.lora_rank <= 32
        or not math.isfinite(args.lora_alpha)
        or args.lora_alpha <= 0
    ):
        parser.error("Invalid finite benchmark limits")
    if args.hf_chunk and args.engine not in ("hf", "hf-shadow"):
        parser.error("--hf-chunk is only supported by HF engines")
    if (args.frozen_head or args.nonzero_adapter) and args.engine != "strict-frozen":
        parser.error("Frozen options require --engine strict-frozen")
    report = {
        "formatVersion": 1,
        "status": "running",
        "engine": args.engine,
        "benchmarkSourceSha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "hardwareQualified": False,
        "environment": {"python": platform.python_version(), "platform": platform.platform()},
        "workload": {
            "maxNewTokens": args.max_new_tokens,
            "maxContext": args.max_context,
            "eosStopping": False,
            "prefixCaching": False,
            "repetitionPenalty": 1.0,
            "dtype": "float16",
            "repeats": args.repeats,
            "hfChunk": args.hf_chunk,
            "frozenHead": args.frozen_head,
            "adapter": {
                "rank": args.lora_rank,
                "alpha": args.lora_alpha,
                "seed": args.adapter_seed,
                "nonzeroRandomB": args.nonzero_adapter,
            }
            if args.engine == "strict-frozen"
            else None,
        },
        "limitations": "Offline fixed-length greedy parent inference; synchronized host wall time, not CUDA kernel "
        "time. Separate environments/builds; unisolated GPUs. 'strict' serializes sequences; 'strict-packed' batches. "
        "No ES lifecycle, native Windows, quality or heterogeneous qualification.",
        "cases": [],
    }
    started = time.perf_counter()
    try:
        engine, prompts, run = load_engine(args, report)
        import torch

        torch.cuda.synchronize()
        report["loadSeconds"] = time.perf_counter() - started
        reference = [run([ids])[0] for ids in prompts]
        report["singleTokens"] = reference
        report["loadAndSinglesPeakAllocatedBytes"] = torch.cuda.max_memory_allocated()
        report["loadAndSinglesPeakReservedBytes"] = torch.cuda.max_memory_reserved()
        for size in args.batch_sizes:
            selected = [i % len(prompts) for i in range(size)]
            torch.cuda.reset_peak_memory_stats()
            result = measure(
                run,
                [prompts[i] for i in selected],
                args.max_new_tokens,
                args.repeats,
                torch.cuda.synchronize,
                before_run=getattr(run, "before_run", None),
            )
            result["peakAllocatedBytesIncludingWarmup"] = torch.cuda.max_memory_allocated()
            result["peakReservedBytesIncludingWarmup"] = torch.cuda.max_memory_reserved()
            result["tokensEqualSingles"] = result["tokens"] == [reference[i] for i in selected]
            report["cases"].append(result)
        report["parentProcessPeakAllocatedBytes"] = max(
            report["loadAndSinglesPeakAllocatedBytes"],
            *(case["peakAllocatedBytesIncludingWarmup"] for case in report["cases"]),
        )
        report["parentProcessPeakReservedBytes"] = max(
            report["loadAndSinglesPeakReservedBytes"],
            *(case["peakReservedBytesIncludingWarmup"] for case in report["cases"]),
        )
        if args.engine in ("strict", "strict-packed", "strict-graph", "strict-integer", "strict-frozen"):
            report["kernelIdentity"] = engine.kernel_identity()
        report["status"] = "ok"
    except Exception as error:
        report.update(status="error", errorType=type(error).__name__, error=str(error)[:3000])
    report["wallSeconds"] = time.perf_counter() - started
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"status": report["status"], "out": str(args.out), "wallSeconds": report["wallSeconds"]}))
    return 0 if report["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
