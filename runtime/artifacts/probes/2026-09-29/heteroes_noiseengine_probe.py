#!/usr/bin/env python3
"""
HeteroES Canonical NoiseEngine v1 probe.

Goal:
  Test a GPU-independent candidate noise recipe before integrating it into ES.

Recipe under test:
  - parameter identity: canonical parameter schema hash + parameter index
  - distribution: standard normal
  - generator: NumPy PCG64
  - generation dtype: float32
  - transport/apply dtype: float16
  - independent deterministic seed per parameter chunk, derived with SHA-256
  - fixed chunk size is part of the contract

Because generation happens on CPU, the resulting noise bytes do not depend on
CUDA device RNG. NumPy version is intentionally recorded and should be pinned.

Run on BOTH machines:
  python heteroes_noiseengine_probe.py probe --output noiseengine_5070ti.json
  python heteroes_noiseengine_probe.py probe --output noiseengine_1660s.json

Then compare:
  python heteroes_noiseengine_probe.py compare \
      noiseengine_5070ti.json noiseengine_1660s.json

Start with the default sampled probe. If it matches, run --full on both machines.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import socket
import sys
import time
from pathlib import Path
from typing import Any

ENGINE_VERSION = "numpy_pcg64_normal_f32_to_f16_v1"
MODEL_ID_DEFAULT = "Qwen/Qwen2.5-0.5B-Instruct"
SEED_DEFAULT = 0
CHUNK_ELEMENTS_DEFAULT = 262_144

PREFERRED_TARGETS = [
    "model.embed_tokens.weight",
    "model.layers.0.self_attn.q_proj.weight",
    "model.layers.12.mlp.up_proj.weight",
    "model.layers.23.mlp.down_proj.weight",
    "model.norm.weight",
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


def build_schema(model) -> list[dict[str, Any]]:
    schema = []
    for index, (name, param) in enumerate(model.named_parameters()):
        if not param.is_floating_point():
            raise TypeError(f"Non-floating parameter: {name} {param.dtype}")
        schema.append(
            {
                "index": index,
                "name": name,
                "shape": list(param.shape),
                "dtype": "torch.float16",
                "numel": int(param.numel()),
            }
        )
    return schema


def derive_chunk_seed(
    *,
    candidate_seed: int,
    schema_hash: str,
    parameter_index: int,
    chunk_index: int,
    chunk_elements: int,
) -> int:
    """
    Derive a 128-bit seed for one parameter chunk.

    Chunk identity is explicit, so generating chunks in a different execution
    order does not change the bytes for a given logical chunk.
    """
    material = (
        f"{ENGINE_VERSION}|"
        f"candidate_seed={candidate_seed}|"
        f"schema={schema_hash}|"
        f"param={parameter_index}|"
        f"chunk={chunk_index}|"
        f"chunk_elements={chunk_elements}"
    ).encode("utf-8")

    digest = hashlib.sha256(material).digest()
    return int.from_bytes(digest[:16], byteorder="little", signed=False)


def generate_chunk_f16_bytes(
    *,
    np,
    candidate_seed: int,
    schema_hash: str,
    parameter_index: int,
    chunk_index: int,
    chunk_elements: int,
    n: int,
) -> bytes:
    derived_seed = derive_chunk_seed(
        candidate_seed=candidate_seed,
        schema_hash=schema_hash,
        parameter_index=parameter_index,
        chunk_index=chunk_index,
        chunk_elements=chunk_elements,
    )

    bitgen = np.random.PCG64(derived_seed)
    rng = np.random.Generator(bitgen)

    # Canonical generation precision.
    values_f32 = rng.standard_normal(n, dtype=np.float32)

    # Canonical application/storage precision for current HeteroES baseline.
    values_f16 = values_f32.astype(np.float16, copy=False)

    return values_f16.tobytes(order="C")


def select_targets(schema: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_name = {x["name"]: x for x in schema}
    selected = []

    for name in PREFERRED_TARGETS:
        if name in by_name:
            selected.append(by_name[name])

    if len(selected) < 3 and schema:
        for idx in sorted({0, len(schema) // 2, len(schema) - 1}):
            item = schema[idx]
            if item not in selected:
                selected.append(item)

    return selected


def probe_parameter(
    *,
    np,
    item: dict[str, Any],
    candidate_seed: int,
    schema_hash: str,
    chunk_elements: int,
    full_parameter: bool,
) -> dict[str, Any]:
    numel = int(item["numel"])
    total_chunks = (numel + chunk_elements - 1) // chunk_elements

    if full_parameter:
        chunk_indexes = list(range(total_chunks))
    else:
        # Probe deterministic representative chunks: beginning, middle, end.
        chunk_indexes = sorted({0, total_chunks // 2, total_chunks - 1})

    aggregate = hashlib.sha256()
    chunk_hashes = {}
    generated_elements = 0

    start = time.perf_counter()

    for chunk_index in chunk_indexes:
        start_elem = chunk_index * chunk_elements
        n = min(chunk_elements, numel - start_elem)

        raw = generate_chunk_f16_bytes(
            np=np,
            candidate_seed=candidate_seed,
            schema_hash=schema_hash,
            parameter_index=int(item["index"]),
            chunk_index=chunk_index,
            chunk_elements=chunk_elements,
            n=n,
        )

        digest = sha256_bytes(raw)
        chunk_hashes[str(chunk_index)] = digest

        aggregate.update(str(chunk_index).encode("ascii"))
        aggregate.update(raw)
        generated_elements += n

    elapsed = time.perf_counter() - start

    return {
        "index": int(item["index"]),
        "name": item["name"],
        "shape": item["shape"],
        "numel": numel,
        "total_chunks": total_chunks,
        "probed_chunks": chunk_indexes,
        "generated_elements": generated_elements,
        "chunk_sha256": chunk_hashes,
        "aggregate_sha256": aggregate.hexdigest(),
        "elapsed_seconds": elapsed,
    }


def run_probe(args: argparse.Namespace) -> int:
    try:
        import numpy as np
        import torch
        import transformers
        from transformers import AutoModelForCausalLM
    except Exception as exc:
        print("ERROR: probe requires numpy, torch, transformers", file=sys.stderr)
        print(repr(exc), file=sys.stderr)
        return 2

    hostname = socket.gethostname()
    output = Path(
        args.output or f"noiseengine_{hostname}.json"
    ).expanduser()

    print("=== HeteroES Canonical NoiseEngine Probe ===")
    print("Engine        :", ENGINE_VERSION)
    print("Host          :", hostname)
    print("Model         :", args.model)
    print("Candidate seed:", args.seed)
    print("Chunk elements:", args.chunk_elements)
    print("Probe mode    :", "FULL" if args.full else "SAMPLED")
    print()

    print("Loading model on CPU only to obtain canonical parameter schema...")
    load_start = time.perf_counter()

    model = AutoModelForCausalLM.from_pretrained(
        args.model,
        dtype=torch.float16,
    )
    model.eval()

    load_seconds = time.perf_counter() - load_start

    schema = build_schema(model)
    schema_hash = canonical_json_hash(schema)

    targets = schema if args.full else select_targets(schema)

    print(f"Model loaded in {load_seconds:.2f}s")
    print("Parameter tensors :", len(schema))
    print("Parameter elements:", sum(x["numel"] for x in schema))
    print("Schema SHA256     :", schema_hash)
    print("Targets           :", len(targets))
    print()

    results = []
    global_hash = hashlib.sha256()
    total_generated = 0
    total_seconds = 0.0

    for i, item in enumerate(targets, start=1):
        print(f"[{i}/{len(targets)}] {item['name']}")

        r = probe_parameter(
            np=np,
            item=item,
            candidate_seed=args.seed,
            schema_hash=schema_hash,
            chunk_elements=args.chunk_elements,
            full_parameter=args.full,
        )

        results.append(r)

        global_hash.update(item["name"].encode("utf-8"))
        global_hash.update(r["aggregate_sha256"].encode("ascii"))
        total_generated += r["generated_elements"]
        total_seconds += r["elapsed_seconds"]

        print("  chunks   :", r["probed_chunks"][:8], "..." if len(r["probed_chunks"]) > 8 else "")
        print("  SHA256   :", r["aggregate_sha256"])
        print(f"  time     : {r['elapsed_seconds']:.3f}s")

    runtime = {
        "hostname": hostname,
        "platform": platform.platform(),
        "python": sys.version,
        "numpy": np.__version__,
        "torch": torch.__version__,
        "transformers": transformers.__version__,
    }

    result = {
        "probe_version": 1,
        "engine": {
            "version": ENGINE_VERSION,
            "distribution": "standard_normal",
            "bit_generator": "numpy.random.PCG64",
            "generation_dtype": "numpy.float32",
            "application_dtype": "numpy.float16 / torch.float16 bytes",
            "seed_derivation": "SHA256 first 128 bits little-endian",
            "candidate_seed": args.seed,
            "chunk_elements": args.chunk_elements,
            "chunk_seed_identity": (
                "engine_version,candidate_seed,schema_hash,"
                "parameter_index,chunk_index,chunk_elements"
            ),
        },
        "runtime": runtime,
        "model": {
            "id": args.model,
            "revision": getattr(model.config, "_commit_hash", None),
            "schema_sha256": schema_hash,
            "parameter_tensors": len(schema),
            "parameter_elements": sum(x["numel"] for x in schema),
        },
        "mode": "full" if args.full else "sampled",
        "target_results": results,
        "global_probe_sha256": global_hash.hexdigest(),
        "generated_elements": total_generated,
        "noise_generation_seconds": total_seconds,
    }

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(result, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print()
    print("=== SUMMARY ===")
    print("NumPy                 :", np.__version__)
    print("Schema SHA256         :", schema_hash)
    print("Global probe SHA256   :", result["global_probe_sha256"])
    print("Generated elements    :", total_generated)
    print(f"Noise generation time : {total_seconds:.3f}s")
    print("Result                :", output)

    return 0


def run_compare(args: argparse.Namespace) -> int:
    left = json.loads(Path(args.left).read_text(encoding="utf-8"))
    right = json.loads(Path(args.right).read_text(encoding="utf-8"))

    checks = {
        "same_engine_version": (
            left["engine"]["version"] == right["engine"]["version"]
        ),
        "same_numpy_version": (
            left["runtime"]["numpy"] == right["runtime"]["numpy"]
        ),
        "same_model": (
            left["model"]["id"] == right["model"]["id"]
        ),
        "same_model_revision": (
            left["model"]["revision"] == right["model"]["revision"]
        ),
        "same_schema": (
            left["model"]["schema_sha256"]
            == right["model"]["schema_sha256"]
        ),
        "same_candidate_seed": (
            left["engine"]["candidate_seed"]
            == right["engine"]["candidate_seed"]
        ),
        "same_chunk_size": (
            left["engine"]["chunk_elements"]
            == right["engine"]["chunk_elements"]
        ),
        "same_mode": left["mode"] == right["mode"],
        "same_noise_bytes": (
            left["global_probe_sha256"]
            == right["global_probe_sha256"]
        ),
    }

    print("=== Canonical NoiseEngine Comparison ===")
    print(
        "LEFT :",
        left["runtime"]["hostname"],
        "| numpy=" + left["runtime"]["numpy"],
        "| torch=" + left["runtime"]["torch"],
    )
    print(
        "RIGHT:",
        right["runtime"]["hostname"],
        "| numpy=" + right["runtime"]["numpy"],
        "| torch=" + right["runtime"]["torch"],
    )
    print()

    width = max(len(k) for k in checks)
    for key, ok in checks.items():
        print(f"{key:<{width}} : {'PASS' if ok else 'DIFF'}")

    print()
    if checks["same_noise_bytes"]:
        print(
            "RESULT: PASS — tested canonical CPU noise bytes are identical "
            "across the two machines."
        )
    else:
        print(
            "RESULT: DIFF — this recipe is not yet portable enough. "
            "Do not integrate it as the canonical NoiseEngine yet."
        )

    # Difference is an experiment outcome, not process failure.
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="HeteroES Canonical NoiseEngine v1 cross-machine probe"
    )
    sub = p.add_subparsers(dest="command", required=True)

    probe = sub.add_parser("probe")
    probe.add_argument("--model", default=MODEL_ID_DEFAULT)
    probe.add_argument("--seed", type=int, default=SEED_DEFAULT)
    probe.add_argument(
        "--chunk-elements",
        type=int,
        default=CHUNK_ELEMENTS_DEFAULT,
    )
    probe.add_argument("--output", default=None)
    probe.add_argument(
        "--full",
        action="store_true",
        help=(
            "Probe every parameter and every chunk. Start without this flag "
            "for a fast representative test."
        ),
    )
    probe.set_defaults(func=run_probe)

    compare = sub.add_parser("compare")
    compare.add_argument("left")
    compare.add_argument("right")
    compare.set_defaults(func=run_compare)

    return p


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
