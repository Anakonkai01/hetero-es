#!/usr/bin/env python3
"""
HeteroES physical-worker compatibility probe.

Run the SAME file on both GPU machines.

Probe:
    python heteroes_compat_probe.py probe --output probe_5070ti.json
    python heteroes_compat_probe.py probe --output probe_1660s.json

Compare (can run on a laptop; torch/transformers are not required for compare):
    python heteroes_compat_probe.py compare probe_5070ti.json probe_1660s.json

What it checks:
- runtime/GPU fingerprint
- model revision and FP16 parameter schema
- sampled canonical weight hashes
- 16-example deterministic base evaluation
- one seed-0 ES perturbation
- sampled/full-target noise hashes across the full RNG traversal
- seed-0 candidate evaluation
- exact canonical restore
- cross-machine comparison with a replay-safety probe

This is a probe, not a proof of full cross-runtime numerical equivalence.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

MODEL_ID_DEFAULT = "Qwen/Qwen2.5-0.5B-Instruct"
SIGMA_DEFAULT = 1e-3
SEED_DEFAULT = 0

SYSTEM_PROMPT = "You are a calculator. Answer with only with number"
MAX_NEW_TOKENS = 16

EXAMPLES = [
    {"question": "What is 17 + 24?", "answer": 41},
    {"question": "What is 6 * 8?", "answer": 48},
    {"question": "What is 91 - 37?", "answer": 54},
    {"question": "What is 12 * 13?", "answer": 156},
    {"question": "What is 137 * 46?", "answer": 6302},
    {"question": "What is 375 + 918 - 427?", "answer": 866},
    {"question": "What is 23 * 17 + 48?", "answer": 439},
    {"question": "What is (144 / 12) * 37?", "answer": 444},
    {"question": "What is 218 * 37?", "answer": 8066},
    {"question": "What is 84 * 19 - 76?", "answer": 1520},
    {"question": "What is 312 * 27 - 145?", "answer": 8279},
    {"question": "What is (73 + 29) * 18?", "answer": 1836},
    {
        "question": (
            "A shop has 48 boxes with 36 pens in each box. "
            "It sells 725 pens. How many pens remain?"
        ),
        "answer": 1003,
    },
    {
        "question": (
            "A school buys 36 packs of notebooks with 24 notebooks per pack. "
            "It distributes 579 notebooks. How many remain?"
        ),
        "answer": 285,
    },
    {
        "question": (
            "A train travels 72 km per hour for 5 hours, "
            "then another 148 km. What is the total distance?"
        ),
        "answer": 508,
    },
    {
        "question": (
            "A factory makes 125 items per hour for 18 hours. "
            "347 items are defective. How many usable items remain?"
        ),
        "answer": 1903,
    },
]

PREFERRED_NOISE_TARGETS = [
    "model.layers.0.self_attn.q_proj.weight",
    "model.layers.12.mlp.up_proj.weight",
    "model.layers.23.mlp.down_proj.weight",
]


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_json_hash(obj: Any) -> str:
    raw = json.dumps(
        obj,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return sha256_bytes(raw)


def safe_cmd(args: list[str]) -> str | None:
    try:
        p = subprocess.run(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=10,
            check=False,
        )
        text = p.stdout.strip()
        return text or None
    except Exception:
        return None


def tensor_sample_sha256(tensor, max_values: int = 4096) -> str:
    import torch

    flat = tensor.detach().reshape(-1)
    n = flat.numel()

    if n <= max_values * 2:
        sample = flat
    else:
        sample = torch.cat((flat[:max_values], flat[-max_values:]))

    raw = (
        sample.contiguous()
        .cpu()
        .view(torch.uint8)
        .numpy()
        .tobytes()
    )
    return sha256_bytes(raw)


def tensor_full_sha256(tensor) -> str:
    import torch

    raw = (
        tensor.detach()
        .contiguous()
        .cpu()
        .view(torch.uint8)
        .numpy()
        .tobytes()
    )
    return sha256_bytes(raw)


def build_parameter_schema(model) -> list[dict[str, Any]]:
    schema = []

    for index, (name, param) in enumerate(model.named_parameters()):
        if not param.is_floating_point():
            raise TypeError(
                f"Unexpected non-floating parameter: {name} ({param.dtype})"
            )

        schema.append(
            {
                "index": index,
                "name": name,
                "shape": list(param.shape),
                "dtype": str(param.dtype),
                "numel": int(param.numel()),
            }
        )

    return schema


def find_alias_groups(model) -> list[list[str]]:
    from collections import defaultdict

    aliases = defaultdict(list)

    try:
        iterator = model.named_parameters(remove_duplicate=False)
    except TypeError:
        iterator = model.named_parameters()

    for name, param in iterator:
        aliases[id(param)].append(name)

    return sorted(
        [sorted(names) for names in aliases.values() if len(names) > 1]
    )


def choose_weight_sample_names(schema: list[dict[str, Any]]) -> list[str]:
    if not schema:
        return []

    indexes = sorted({0, len(schema) // 2, len(schema) - 1})
    return [schema[i]["name"] for i in indexes]


def choose_noise_targets(schema: list[dict[str, Any]]) -> list[str]:
    names = {item["name"] for item in schema}
    targets = [name for name in PREFERRED_NOISE_TARGETS if name in names]

    if len(targets) >= 3:
        return targets

    fallback = choose_weight_sample_names(schema)
    for name in fallback:
        if name not in targets:
            targets.append(name)

    return targets[:3]


def capture_canonical_parameters(model) -> dict[str, Any]:
    snapshot = {}

    for name, param in model.named_parameters():
        snapshot[name] = param.detach().cpu().clone()

    return snapshot


def restore_canonical_and_verify(model, snapshot) -> tuple[float, str | None]:
    import torch

    max_diff = 0.0
    worst = None

    with torch.no_grad():
        for name, param in model.named_parameters():
            if name not in snapshot:
                raise KeyError(f"Missing canonical parameter: {name}")

            source_cpu = snapshot[name]

            if tuple(source_cpu.shape) != tuple(param.shape):
                raise ValueError(
                    f"Shape mismatch for {name}: "
                    f"snapshot={tuple(source_cpu.shape)}, "
                    f"model={tuple(param.shape)}"
                )

            source = source_cpu.to(param.device, dtype=param.dtype)
            param.copy_(source)

            diff = (param - source).abs().max().item()
            if diff > max_diff:
                max_diff = diff
                worst = name

            del source

    if max_diff == 0.0:
        worst = None

    return float(max_diff), worst


def extract_integer(text: str) -> int | None:
    numbers = re.findall(r"-?\d+", text.replace(",", ""))
    if not numbers:
        return None
    return int(numbers[-1])


def generate_answer(model, tokenizer, question: str) -> str:
    import torch

    device = next(model.parameters()).device

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": question},
    ]

    inputs = tokenizer.apply_chat_template(
        messages,
        return_tensors="pt",
        return_dict=True,
        add_generation_prompt=True,
        tokenize=True,
    )

    inputs = {key: value.to(device) for key, value in inputs.items()}

    with torch.no_grad():
        output_ids = model.generate(
            **inputs,
            max_new_tokens=MAX_NEW_TOKENS,
            do_sample=False,
        )

    prompt_length = inputs["input_ids"].shape[1]
    generated_ids = output_ids[:, prompt_length:]

    answer = tokenizer.batch_decode(
        generated_ids,
        skip_special_tokens=True,
    )[0]

    return answer.strip()


def evaluate_model(model, tokenizer) -> tuple[float, list[dict[str, Any]]]:
    records = []
    total_reward = 0.0

    for example in EXAMPLES:
        output_text = generate_answer(
            model,
            tokenizer,
            example["question"],
        )
        prediction = extract_integer(output_text)
        reward = 1.0 if prediction == example["answer"] else 0.0
        total_reward += reward

        records.append(
            {
                "question": example["question"],
                "expected": example["answer"],
                "output_text": output_text,
                "prediction": prediction,
                "reward": reward,
            }
        )

    return total_reward / len(EXAMPLES), records


def apply_perturbation_with_noise_probe(
    model,
    *,
    seed: int,
    sigma: float,
    target_names: list[str],
) -> dict[str, Any]:
    """
    Uses the same logical recipe as the current notebook:
      one CUDA Generator -> manual_seed(seed) -> parameter traversal ->
      torch.randn_like(param, generator=g) -> param.add_(epsilon, alpha=sigma)

    It also computes:
    - full SHA256 for a few selected noise tensors
    - an aggregate sampled hash (first/last values from every noise tensor)
    """
    import torch

    device = next(model.parameters()).device
    generator = torch.Generator(device=device)
    generator.manual_seed(seed)

    target_set = set(target_names)
    target_hashes: dict[str, str] = {}
    stream_hasher = hashlib.sha256()
    visited = 0

    torch.cuda.reset_peak_memory_stats()

    start = time.perf_counter()

    with torch.no_grad():
        for name, param in model.named_parameters():
            if not param.is_floating_point():
                raise TypeError(
                    f"Unexpected non-floating parameter: {name} ({param.dtype})"
                )

            epsilon = torch.randn_like(
                param,
                generator=generator,
            )

            # Cover the full parameter traversal without copying all noise to CPU.
            flat = epsilon.reshape(-1)
            sample_n = min(256, flat.numel())

            stream_hasher.update(name.encode("utf-8"))
            stream_hasher.update(str(tuple(param.shape)).encode("utf-8"))
            stream_hasher.update(str(param.dtype).encode("utf-8"))

            if sample_n:
                head = flat[:sample_n]
                stream_hasher.update(
                    head.contiguous()
                    .cpu()
                    .view(torch.uint8)
                    .numpy()
                    .tobytes()
                )

                if flat.numel() > sample_n:
                    tail = flat[-sample_n:]
                    stream_hasher.update(
                        tail.contiguous()
                        .cpu()
                        .view(torch.uint8)
                        .numpy()
                        .tobytes()
                    )

            if name in target_set:
                target_hashes[name] = tensor_full_sha256(epsilon)

            param.add_(epsilon, alpha=sigma)
            visited += 1
            del epsilon

    torch.cuda.synchronize()

    elapsed = time.perf_counter() - start

    missing = sorted(target_set - set(target_hashes))
    if missing:
        raise RuntimeError(f"Noise targets were not visited: {missing}")

    return {
        "seed": seed,
        "sigma": sigma,
        "visited_parameter_tensors": visited,
        "stream_sample_sha256": stream_hasher.hexdigest(),
        "target_full_sha256": target_hashes,
        "elapsed_seconds": elapsed,
        "peak_allocated_gb": (
            torch.cuda.max_memory_allocated() / (1024 ** 3)
        ),
    }


def gpu_memory_snapshot() -> dict[str, float]:
    import torch

    free, total = torch.cuda.mem_get_info()

    return {
        "allocated_gb": torch.cuda.memory_allocated() / (1024 ** 3),
        "reserved_gb": torch.cuda.memory_reserved() / (1024 ** 3),
        "free_gb": free / (1024 ** 3),
        "total_gb": total / (1024 ** 3),
    }


def run_probe(args: argparse.Namespace) -> int:
    try:
        import torch
        import transformers
        from transformers import AutoModelForCausalLM, AutoTokenizer
    except Exception as exc:
        print(
            "ERROR: probe mode requires torch and transformers in the "
            "active Python environment.",
            file=sys.stderr,
        )
        print(repr(exc), file=sys.stderr)
        return 2

    if not torch.cuda.is_available():
        print("ERROR: CUDA is not available.", file=sys.stderr)
        return 2

    if args.dtype != "float16":
        print(
            "ERROR: this probe intentionally supports float16 only so it "
            "matches the current modified reference notebook.",
            file=sys.stderr,
        )
        return 2

    dtype = torch.float16
    device = "cuda"

    hostname = socket.gethostname()
    output_path = Path(
        args.output or f"probe_{hostname}.json"
    ).expanduser()

    print("=== HeteroES Compatibility Probe ===")
    print("Host      :", hostname)
    print("Model     :", args.model)
    print("dtype     :", dtype)
    print("Seed      :", args.seed)
    print("Sigma     :", args.sigma)
    print()

    nvidia_driver = safe_cmd(
        [
            "nvidia-smi",
            "--query-gpu=driver_version",
            "--format=csv,noheader",
        ]
    )

    runtime = {
        "hostname": hostname,
        "platform": platform.platform(),
        "python": sys.version,
        "python_executable": sys.executable,
        "torch": torch.__version__,
        "transformers": transformers.__version__,
        "torch_cuda": torch.version.cuda,
        "nvidia_driver": nvidia_driver,
        "gpu_name": torch.cuda.get_device_name(0),
        "gpu_capability": list(torch.cuda.get_device_capability(0)),
        "gpu_total_memory_gb": (
            torch.cuda.get_device_properties(0).total_memory / (1024 ** 3)
        ),
    }

    print("Runtime:")
    for key, value in runtime.items():
        print(f"  {key}: {value}")
    print()

    print("Loading model/tokenizer...")
    load_start = time.perf_counter()

    model = AutoModelForCausalLM.from_pretrained(
        args.model,
        dtype=dtype,
    ).to(device)

    tokenizer = AutoTokenizer.from_pretrained(args.model)
    model.eval()
    torch.cuda.synchronize()

    load_seconds = time.perf_counter() - load_start

    model_revision = getattr(model.config, "_commit_hash", None)
    tokenizer_revision = None
    try:
        tokenizer_revision = tokenizer.init_kwargs.get("_commit_hash")
    except Exception:
        pass

    print(f"Loaded in {load_seconds:.2f}s")
    print("Model revision    :", model_revision)
    print("Tokenizer revision:", tokenizer_revision)

    schema = build_parameter_schema(model)
    schema_hash = canonical_json_hash(schema)
    parameter_elements = sum(item["numel"] for item in schema)
    alias_groups = find_alias_groups(model)

    sample_names = choose_weight_sample_names(schema)
    named_params = dict(model.named_parameters())

    canonical_weight_sample_hashes = {
        name: tensor_sample_sha256(named_params[name])
        for name in sample_names
    }

    noise_targets = choose_noise_targets(schema)

    structural = {
        "model_id": args.model,
        "model_revision": model_revision,
        "tokenizer_revision": tokenizer_revision,
        "dtype": str(next(model.parameters()).dtype),
        "parameter_tensors": len(schema),
        "parameter_elements": parameter_elements,
        "schema_sha256": schema_hash,
        "alias_groups": alias_groups,
        "canonical_weight_sample_sha256": canonical_weight_sample_hashes,
        "noise_targets": noise_targets,
    }

    print()
    print("Structure:")
    print("  dtype             :", structural["dtype"])
    print("  parameter tensors :", len(schema))
    print("  parameter elements:", parameter_elements)
    print("  schema SHA256     :", schema_hash)
    print("  alias groups      :", len(alias_groups))

    workload = {
        "system_prompt": SYSTEM_PROMPT,
        "max_new_tokens": MAX_NEW_TOKENS,
        "do_sample": False,
        "reward_type": "exact_integer_match",
        "examples": EXAMPLES,
    }
    workload_hash = canonical_json_hash(workload)

    print()
    print("Running base 16-example evaluation...")
    base_start = time.perf_counter()
    base_reward, base_records = evaluate_model(model, tokenizer)
    torch.cuda.synchronize()
    base_seconds = time.perf_counter() - base_start

    print("Base reward:", base_reward)
    print(f"Base eval  : {base_seconds:.2f}s")

    print()
    print("Capturing canonical CPU snapshot...")
    snapshot_start = time.perf_counter()
    canonical_snapshot = capture_canonical_parameters(model)
    snapshot_seconds = time.perf_counter() - snapshot_start
    print(f"Snapshot   : {snapshot_seconds:.2f}s")

    memory_before_perturb = gpu_memory_snapshot()

    print()
    print("Applying seed-0 perturbation + noise probe...")
    noise_info = apply_perturbation_with_noise_probe(
        model,
        seed=args.seed,
        sigma=args.sigma,
        target_names=noise_targets,
    )

    perturbed_weight_sample_hashes = {
        name: tensor_sample_sha256(dict(model.named_parameters())[name])
        for name in sample_names
    }

    changed_sampled_weights = any(
        canonical_weight_sample_hashes[name]
        != perturbed_weight_sample_hashes[name]
        for name in sample_names
    )

    print("Noise stream sample SHA256:", noise_info["stream_sample_sha256"])
    for name, digest in noise_info["target_full_sha256"].items():
        print("Noise target SHA256:", name, digest)
    print("Sampled weights changed:", changed_sampled_weights)

    print()
    print("Running perturbed candidate evaluation...")
    candidate_start = time.perf_counter()
    candidate_reward, candidate_records = evaluate_model(model, tokenizer)
    torch.cuda.synchronize()
    candidate_seconds = time.perf_counter() - candidate_start

    print("Candidate reward:", candidate_reward)
    print(f"Candidate eval  : {candidate_seconds:.2f}s")

    print()
    print("Restoring canonical model and verifying exactness...")
    restore_start = time.perf_counter()
    restore_diff, restore_worst = restore_canonical_and_verify(
        model,
        canonical_snapshot,
    )
    torch.cuda.synchronize()
    restore_seconds = time.perf_counter() - restore_start

    restored_weight_sample_hashes = {
        name: tensor_sample_sha256(dict(model.named_parameters())[name])
        for name in sample_names
    }

    sampled_weight_restore_match = (
        restored_weight_sample_hashes
        == canonical_weight_sample_hashes
    )

    print("Restore max diff:", restore_diff)
    print("Restore worst   :", restore_worst)
    print("Sample hashes restored:", sampled_weight_restore_match)

    result = {
        "probe_version": 1,
        "runtime": runtime,
        "structural": structural,
        "workload": {
            "sha256": workload_hash,
            "example_count": len(EXAMPLES),
            "system_prompt": SYSTEM_PROMPT,
            "max_new_tokens": MAX_NEW_TOKENS,
            "do_sample": False,
            "reward_type": "exact_integer_match",
        },
        "timing_seconds": {
            "model_load": load_seconds,
            "base_eval": base_seconds,
            "canonical_snapshot": snapshot_seconds,
            "candidate_eval": candidate_seconds,
            "restore": restore_seconds,
        },
        "memory_before_perturb": memory_before_perturb,
        "base_evaluation": {
            "mean_reward": base_reward,
            "records": base_records,
        },
        "noise": noise_info,
        "perturbation": {
            "sampled_weights_changed": changed_sampled_weights,
            "perturbed_weight_sample_sha256": (
                perturbed_weight_sample_hashes
            ),
        },
        "candidate_evaluation": {
            "seed": args.seed,
            "sigma": args.sigma,
            "mean_reward": candidate_reward,
            "records": candidate_records,
        },
        "restore": {
            "max_diff": restore_diff,
            "worst_parameter": restore_worst,
            "exact": restore_diff == 0.0,
            "sample_hashes_match_canonical": sampled_weight_restore_match,
            "restored_weight_sample_sha256": (
                restored_weight_sample_hashes
            ),
        },
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(result, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print()
    print("=== SUMMARY ===")
    print("GPU                 :", runtime["gpu_name"])
    print("Schema SHA256       :", schema_hash)
    print("Workload SHA256     :", workload_hash)
    print("Base reward         :", base_reward)
    print("Candidate reward    :", candidate_reward)
    print("Noise sample SHA256 :", noise_info["stream_sample_sha256"])
    print("Restore exact       :", restore_diff == 0.0)
    print("Result              :", output_path)

    return 0


def load_json(path: str) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def get_predictions(data: dict[str, Any], section: str) -> list[Any]:
    return [
        record.get("prediction")
        for record in data.get(section, {}).get("records", [])
    ]


def compare_equal(a: Any, b: Any) -> bool:
    return a == b


def run_compare(args: argparse.Namespace) -> int:
    left = load_json(args.left)
    right = load_json(args.right)

    left_host = left.get("runtime", {}).get("hostname", args.left)
    right_host = right.get("runtime", {}).get("hostname", args.right)

    def pair(path: tuple[str, ...]) -> tuple[Any, Any]:
        def read(obj: dict[str, Any]) -> Any:
            cur: Any = obj
            for key in path:
                if not isinstance(cur, dict):
                    return None
                cur = cur.get(key)
            return cur

        return read(left), read(right)

    checks: dict[str, bool] = {}

    for name, path in {
        "same_model_id": ("structural", "model_id"),
        "same_model_revision": ("structural", "model_revision"),
        "same_dtype": ("structural", "dtype"),
        "same_schema": ("structural", "schema_sha256"),
        "same_parameter_count": ("structural", "parameter_elements"),
        "same_weight_samples": (
            "structural",
            "canonical_weight_sample_sha256",
        ),
        "same_workload": ("workload", "sha256"),
        "same_noise_stream_sample": (
            "noise",
            "stream_sample_sha256",
        ),
        "same_noise_target_hashes": (
            "noise",
            "target_full_sha256",
        ),
        "same_base_reward": (
            "base_evaluation",
            "mean_reward",
        ),
        "same_candidate_reward": (
            "candidate_evaluation",
            "mean_reward",
        ),
    }.items():
        a, b = pair(path)
        checks[name] = compare_equal(a, b)

    checks["same_base_predictions"] = (
        get_predictions(left, "base_evaluation")
        == get_predictions(right, "base_evaluation")
    )
    checks["same_candidate_predictions"] = (
        get_predictions(left, "candidate_evaluation")
        == get_predictions(right, "candidate_evaluation")
    )

    left_restore = bool(left.get("restore", {}).get("exact"))
    right_restore = bool(right.get("restore", {}).get("exact"))
    checks["left_restore_exact"] = left_restore
    checks["right_restore_exact"] = right_restore

    structural_ok = all(
        checks[name]
        for name in [
            "same_model_id",
            "same_dtype",
            "same_schema",
            "same_parameter_count",
            "same_weight_samples",
            "same_workload",
        ]
    )

    restore_ok = left_restore and right_restore

    # This is deliberately called a probe, not a formal guarantee.
    replay_probe_pass = all(
        [
            structural_ok,
            restore_ok,
            checks["same_noise_stream_sample"],
            checks["same_noise_target_hashes"],
        ]
    )

    behavior_match = all(
        [
            checks["same_base_reward"],
            checks["same_candidate_reward"],
            checks["same_base_predictions"],
            checks["same_candidate_predictions"],
        ]
    )

    report = {
        "left": {
            "file": args.left,
            "hostname": left_host,
            "gpu": left.get("runtime", {}).get("gpu_name"),
            "torch": left.get("runtime", {}).get("torch"),
            "torch_cuda": left.get("runtime", {}).get("torch_cuda"),
            "transformers": left.get("runtime", {}).get("transformers"),
        },
        "right": {
            "file": args.right,
            "hostname": right_host,
            "gpu": right.get("runtime", {}).get("gpu_name"),
            "torch": right.get("runtime", {}).get("torch"),
            "torch_cuda": right.get("runtime", {}).get("torch_cuda"),
            "transformers": right.get("runtime", {}).get("transformers"),
        },
        "checks": checks,
        "summary": {
            "structural_contract_match": structural_ok,
            "both_restore_exact": restore_ok,
            "behavior_match": behavior_match,
            "replay_probe_pass": replay_probe_pass,
            "interpretation": (
                "Replay probe PASS on the tested recipe."
                if replay_probe_pass
                else (
                    "Replay probe does NOT match across these runtimes. "
                    "Do not assume seed-only replay is safe yet."
                )
            ),
        },
    }

    print("=== HeteroES Probe Comparison ===")
    print(
        f"LEFT : {left_host} | "
        f"{report['left']['gpu']} | "
        f"torch={report['left']['torch']} | "
        f"cuda={report['left']['torch_cuda']} | "
        f"transformers={report['left']['transformers']}"
    )
    print(
        f"RIGHT: {right_host} | "
        f"{report['right']['gpu']} | "
        f"torch={report['right']['torch']} | "
        f"cuda={report['right']['torch_cuda']} | "
        f"transformers={report['right']['transformers']}"
    )
    print()

    width = max(len(name) for name in checks)
    for name, passed in checks.items():
        print(f"{name:<{width}} : {'PASS' if passed else 'DIFF'}")

    print()
    print("Structural contract match:", structural_ok)
    print("Both restore exact       :", restore_ok)
    print("Behavior match           :", behavior_match)
    print("Replay probe pass        :", replay_probe_pass)
    print()
    print(report["summary"]["interpretation"])

    if args.output:
        out = Path(args.output).expanduser()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            json.dumps(report, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        print("Comparison JSON          :", out)

    # Differences are experiment results, not script failures.
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="HeteroES physical-worker compatibility probe"
    )

    sub = parser.add_subparsers(dest="command", required=True)

    probe = sub.add_parser(
        "probe",
        help="Run the compatibility probe on one GPU worker",
    )
    probe.add_argument(
        "--model",
        default=MODEL_ID_DEFAULT,
        help=f"HF model id (default: {MODEL_ID_DEFAULT})",
    )
    probe.add_argument(
        "--dtype",
        default="float16",
        choices=["float16"],
        help="Pinned to float16 to match the modified reference",
    )
    probe.add_argument(
        "--seed",
        type=int,
        default=SEED_DEFAULT,
        help=f"Candidate/noise seed (default: {SEED_DEFAULT})",
    )
    probe.add_argument(
        "--sigma",
        type=float,
        default=SIGMA_DEFAULT,
        help=f"ES sigma (default: {SIGMA_DEFAULT})",
    )
    probe.add_argument(
        "--output",
        default=None,
        help="Output JSON path (default: probe_<hostname>.json)",
    )
    probe.set_defaults(func=run_probe)

    compare = sub.add_parser(
        "compare",
        help="Compare two JSON probe results",
    )
    compare.add_argument("left", help="First probe JSON")
    compare.add_argument("right", help="Second probe JSON")
    compare.add_argument(
        "--output",
        default=None,
        help="Optional comparison JSON output",
    )
    compare.set_defaults(func=run_compare)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
