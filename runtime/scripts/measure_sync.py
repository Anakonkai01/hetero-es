#!/usr/bin/env python3
"""
Measure only the link and the full synchronization of THIS machine against `scripts/serve_weights.py` (the `sync` block of a profile, without the hours of the chunk probes).

    HETEROES_TOKEN=... python scripts/measure_sync.py --model-path <snapshot dir> --worker-id worker-3060 --sync-url http://<host>:<port> --sync-sha256 <hash> --out sync-3060.json [--repeats 3]

It does what a worker does at the start of a generation: download the file (the hash is checked while the bytes arrive), load it into the model, make it the parent (compared with the
file, not hashed). `--repeats` times; the output has every repeat and the median. The result is `sync` in the shape that `heteroes.admission` reads, so that it can be put in a profile
that lacks it (say so where you do). The output file must not exist.
"""
import argparse
import json
import os
import statistics
import sys
import time
from pathlib import Path


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--model-path", required=True)
    parser.add_argument("--worker-id", required=True)
    parser.add_argument("--sync-url", required=True)
    parser.add_argument("--sync-sha256", required=True)
    parser.add_argument("--sync-dir", default=str(Path.home() / ".cache" / "heteroes" / "measure-sync"))
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    if Path(args.out).exists():
        print(f"error: {args.out} already exists; evidence is never overwritten", file=sys.stderr)
        return 2

    import torch

    from heteroes.executor import CandidateExecutor
    from heteroes.http_transport import HttpClient
    from heteroes.model.loading import build_recipe, load_pinned_model
    from heteroes.model.weights_io import load_weights_
    from heteroes.runtime_info import code_info, environment_info
    from heteroes.worker_runtime import download_weights

    device = "cuda" if torch.cuda.is_available() else "cpu"
    loaded = load_pinned_model(args.model_path, device)
    recipe = build_recipe(loaded, sigma=1e-3, eval_dtype="float32")
    executor = CandidateExecutor(loaded.model, loaded.tokenizer, loaded.schema, recipe)
    client = HttpClient(args.sync_url, token=os.environ.get("HETEROES_TOKEN") or None, timeout=60.0)
    rtts = []
    for _ in range(20):
        start = time.perf_counter()
        client.get_json("/v1/health")
        rtts.append(time.perf_counter() - start)
    runs = []
    for _ in range(args.repeats):
        directory = Path(args.sync_dir)
        start = time.perf_counter()
        path = download_weights(client, args.sync_sha256, directory)
        transferred = time.perf_counter()
        load_weights_(loaded.model, loaded.schema, path, args.sync_sha256, already_verified=True)
        loaded_at = time.perf_counter()
        executor.reset_parent(args.sync_sha256, verified_file=path)
        done = time.perf_counter()
        size = path.stat().st_size
        path.unlink()
        runs.append({"transfer_seconds": transferred - start, "load_seconds": loaded_at - transferred, "rehash_seconds": done - loaded_at,
                     "total_seconds": done - start, "weights_bytes": size, "throughput_mb_per_second": size / 1e6 / (transferred - start)})
    median = {key: statistics.median(run[key] for run in runs) for key in runs[0]}
    sync = {"url": args.sync_url, "rtt_median_seconds": statistics.median(rtts), "rtt_max_seconds": max(rtts), "weights_sha256": args.sync_sha256,
            **median, "repeats": runs}
    result = {"worker_id": args.worker_id, "measured_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "environment": environment_info(device),
              "code": code_info(), "sync": sync}
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "x", encoding="utf-8") as file:
        json.dump(result, file, indent=2)
        file.write("\n")
    print(json.dumps({key: sync[key] for key in ("rtt_median_seconds", "transfer_seconds", "load_seconds", "rehash_seconds", "total_seconds", "throughput_mb_per_second")}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
