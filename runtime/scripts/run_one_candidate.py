#!/usr/bin/env python3
"""
Run ONE ES candidate end to end on this machine and write a JSON record of it (step 6 of the plan).

    python scripts/run_one_candidate.py --model-path <snapshot dir of Qwen2.5-0.5B-Instruct@7ae55760...> \
        --seed 0 --sigma 1e-3 --repeat 2 --output artifacts/regression/<date>-one-candidate/5070ti.json

The same file is run on the other machine at the same commit (step 7) and the two records are compared.
The record holds the recipe and its hash (manifest v1, heteroes/manifest.py), the candidate descriptor and the result of the noise self-test.
It refuses to overwrite an existing output file (evidence is never overwritten) and refuses a model
directory whose name is not the pinned revision.
"""
import argparse
import json
import platform
import socket
import subprocess
import sys
from pathlib import Path

PINNED_REVISION = "7ae557604adf67be50417f59c2c2f167def9a775"
FORMAT_VERSION = 2
MODEL_ID = "Qwen/Qwen2.5-0.5B-Instruct"
REPO_ROOT = Path(__file__).resolve().parents[1]


def fail(message: str) -> None:
    print(f"error: {message}", file=sys.stderr)
    sys.exit(2)


def run_command(arguments: list[str]) -> str | None:
    try:
        completed = subprocess.run(arguments, capture_output=True, text=True, cwd=REPO_ROOT, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    return completed.stdout.strip() if completed.returncode == 0 else None


def code_info() -> dict:
    commit = run_command(["git", "rev-parse", "HEAD"])
    status = run_command(["git", "status", "--porcelain"])
    # untracked files count as dirty: they can change what runs
    return {"git_commit": commit, "git_dirty": None if status is None else bool(status)}


def environment_info(device: str) -> dict:
    import numpy
    import torch
    import transformers

    info = {
        "hostname": socket.gethostname(),
        "platform": platform.platform(),
        "python": platform.python_version(),
        "torch": torch.__version__,
        "torch_cuda": torch.version.cuda,
        "numpy": numpy.__version__,
        "transformers": transformers.__version__,
        "device": device,
        "gpu_name": None,
        "gpu_capability": None,
        "gpu_total_memory_bytes": None,
        "nvidia_driver": None,
    }
    if device == "cuda":
        properties = torch.cuda.get_device_properties(0)
        info["gpu_name"] = properties.name
        info["gpu_capability"] = [properties.major, properties.minor]
        info["gpu_total_memory_bytes"] = properties.total_memory
        info["nvidia_driver"] = run_command(["nvidia-smi", "--query-gpu=driver_version", "--format=csv,noheader"])
    return info


def comparable(run: dict) -> dict:
    # everything except the clock and the memory: those differ from run to run by nature
    return {key: value for key, value in run.items() if key not in ("timing_seconds", "gpu_memory")}


def runs_identical(runs: list[dict]) -> bool:
    """True if every run gave the same record, apart from the clock and the memory."""
    return all(comparable(run) == comparable(runs[0]) for run in runs)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--model-path", required=True, help="snapshot directory named after the pinned revision")
    parser.add_argument("--output", required=True, help="JSON file to create (must not exist)")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--experiment-id", default="regression", help="name of the experiment in the candidate descriptor")
    parser.add_argument("--sigma", type=float, default=1e-3)
    parser.add_argument("--chunk-elements", type=int, default=None, help="default: the contract value")
    parser.add_argument("--repeat", type=int, default=2, help="how many times the same candidate is run in this process")
    parser.add_argument("--device", choices=["cuda", "cpu"], default=None, help="default: cuda if available")
    args = parser.parse_args(argv)

    # cheap checks first, before loading anything
    model_path = Path(args.model_path)
    revision = model_path.resolve().name
    if revision != PINNED_REVISION:
        fail(f"the model directory must be named after the pinned revision {PINNED_REVISION}, got '{revision}'")
    output = Path(args.output)
    if output.exists():
        fail(f"{output} already exists; evidence files are never overwritten")
    if args.repeat < 1:
        fail("--repeat must be at least 1")

    import time

    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    from heteroes.canonical import canonical_json_hash
    from heteroes.es.update import DEFAULT_ETA
    from heteroes.eval.candidate import run_candidate
    from heteroes.eval.workload import workload_hash
    from heteroes.manifest import CandidateDescriptor, Recipe, generation_config_sha256
    from heteroes.model.schema import build_parameter_schema
    from heteroes.noise.contracts import DEFAULT_CHUNK_ELEMENTS, ENGINE_VERSION
    from heteroes.noise.selftest import EXPECTED_NOISE_FINGERPRINT, compute_noise_fingerprint

    # This machine must generate the canonical noise bytes, or nothing it computes can be trusted (about 15 ms).
    start = time.perf_counter()
    computed_fingerprint = compute_noise_fingerprint()
    selftest = {
        "passed": computed_fingerprint == EXPECTED_NOISE_FINGERPRINT,
        "computed_fingerprint": computed_fingerprint,
        "expected_fingerprint": EXPECTED_NOISE_FINGERPRINT,
        "elapsed_seconds": time.perf_counter() - start,
    }
    if not selftest["passed"]:
        fail("the noise self-test failed: this NumPy does not generate the canonical noise bytes")

    device = args.device or ("cuda" if torch.cuda.is_available() else "cpu")
    chunk_elements = args.chunk_elements or DEFAULT_CHUNK_ELEMENTS

    model = AutoModelForCausalLM.from_pretrained(model_path, dtype=torch.float16).to(device)
    tokenizer = AutoTokenizer.from_pretrained(model_path)
    schema = build_parameter_schema(model)
    generation_config = model.generation_config.to_dict()

    recipe = Recipe(
        model_id=MODEL_ID,
        model_revision=revision,
        tokenizer_revision=revision,   # the tokenizer files come from the same snapshot directory
        dtype=str(next(model.parameters()).dtype),
        schema_hash=schema.hash,
        engine_version=ENGINE_VERSION,
        chunk_elements=chunk_elements,
        noise_fingerprint=EXPECTED_NOISE_FINGERPRINT,
        sigma=args.sigma,
        reward_eta=DEFAULT_ETA,
        workload_hash=workload_hash(),
        generation_config_sha256=generation_config_sha256(generation_config),
        eval_dtype="float16",      # this script evaluates the live FP16 model (the regression of steps 6 to 9)
    )

    runs = []
    for index in range(args.repeat):
        print(f"candidate run {index + 1} of {args.repeat} (seed {args.seed}, sigma {args.sigma}) ...", flush=True)
        runs.append(run_candidate(model, tokenizer, schema, args.seed, args.sigma, chunk_elements))

    descriptor = CandidateDescriptor(
        recipe_hash=recipe.hash,
        parent_weights_sha256=runs[0]["weights_sha256"]["original"],
        experiment_id=args.experiment_id,
        generation=0,
        index=0,
        seed=args.seed,
    )

    record = {
        "format_version": FORMAT_VERSION,
        "environment": environment_info(device),
        "code": code_info(),
        "model": {
            "path": str(model_path),
            "revision": revision,
            "tokenizer_revision": revision,   # the tokenizer files come from the same snapshot directory
            "dtype": str(next(model.parameters()).dtype),
            "generation_config": generation_config,
            "generation_config_sha256": generation_config_sha256(generation_config),   # the SET values (see manifest.py)
            "generation_config_raw_sha256": canonical_json_hash(generation_config),    # differs between library versions
        },
        "noise_selftest": selftest,
        "recipe": recipe.to_dict(),
        "recipe_hash": recipe.hash,
        "descriptor": descriptor.to_dict(),
        "runs": runs,
        "repeat_identical": runs_identical(runs),
    }

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(record, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    print(f"wrote {output}; repeat_identical={record['repeat_identical']}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
