"""Record the answer texts of GSM8K candidates at several chunks on this GPU, the way a Recipe v3 run evaluates them.

    python chunk_probe.py run <model dir> <dataset.json> <out.json> [--rows 128] [--chunks 16,64,128] [--candidates 4]
    python chunk_probe.py compare <a.json> <b.json> [...]

RUNTIME-TODO `chunk-128`, ADR-010: a chunk may be offered only when the texts it gives are the texts every other GPU gives
at every allowed chunk. The rows are the first `--rows` of the dataset's train split, one batch (FP32 evaluation, the
run's decoder and prompt). The conditions are `--candidates` perturbed candidates (sigma 1e-3, seeds 7001...), each
with +sigma and -sigma. Per text the record keeps its SHA-256 and length. The output file must not exist (evidence is never
overwritten).
"""

import argparse
import hashlib
import json
import platform
import sys
import tempfile
import time
from pathlib import Path


def run(args):
    out = Path(args.out)
    if out.exists():
        sys.exit(f"{out} already exists")
    import torch

    from heteroes.executor import CandidateExecutor
    from heteroes.manifest import CandidateDescriptor
    from heteroes.v3.data import open_dataset
    from heteroes.v3.local import prepare

    dataset = open_dataset(args.dataset)
    rows = [dict(dataset["splits"]["train"][i]) for i in range(args.rows)]
    chunks = [int(c) for c in args.chunks.split(",")]
    with tempfile.TemporaryDirectory(prefix="chunk-probe-") as temporary:
        root = Path(temporary)
        files = {}
        others = {n: [dict(dataset["splits"][n][i]) for i in range(4)] for n in ("validation", "test")}
        for name, items in (("train", rows), ("validation", others["validation"]), ("test", others["test"])):
            files[name] = root / f"{name}.jsonl"
            files[name].write_text("".join(json.dumps(r) + "\n" for r in items))
        config = {
            "model": {"path": args.model, "id": "Qwen/Qwen2.5-0.5B-Instruct"},
            "data": {"splits": {k: str(v) for k, v in files.items()}, "promptField": "prompt", "batchSize": args.rows},
            "weightSpace": {"kind": "full"},
            "sigma": {"initial": 1e-3},
            "maxNewTokens": args.max_new_tokens,
            "population": 2,
            "generations": 1,
            "alpha": 1e-3,
            "scorer": {"kind": "declarative", "name": "answer-line-last-number"},
            "evalDtype": "float32",
        }
        ready = prepare(config, root / "run", "cuda")
        run_, data = ready["run"], ready["dataset"]
        executor = CandidateExecutor(
            ready["model"], ready["tokenizer"], ready["schema"], run_, dataset=data, return_completions=True
        )
        executor.set_generation(0, run_.context(data, 0))
        conditions = [(seed, sign) for seed in range(7001, 7001 + args.candidates) for sign in (1, -1)]
        record = {
            "gpu": torch.cuda.get_device_name(0),
            "torch": torch.__version__,
            "host": platform.node(),
            "rows": args.rows,
            "maxNewTokens": args.max_new_tokens,
            "chunks": {},
        }
        for chunk in chunks:
            texts, seconds = {}, 0.0
            for index, (seed, sign) in enumerate(conditions):
                descriptor = CandidateDescriptor(run_.hash, executor.parent_sha256, "chunk-probe", 0, index, seed, sign)
                torch.cuda.reset_peak_memory_stats()
                start = time.perf_counter()
                executor(descriptor, chunk=chunk)
                seconds += time.perf_counter() - start
                texts[f"{seed}{'+' if sign > 0 else '-'}"] = [
                    [hashlib.sha256(t.encode()).hexdigest(), len(t)] for t in executor.last_completions
                ]
            record["chunks"][str(chunk)] = {
                "texts": texts,
                "secondsPerCondition": round(seconds / len(conditions), 2),
                "peakBytes": int(torch.cuda.max_memory_allocated()),
            }
            print(f"chunk {chunk}: {record['chunks'][str(chunk)]['secondsPerCondition']} s per condition", flush=True)
    out.write_text(json.dumps(record, indent=1))


def compare(args):
    records = [json.loads(Path(p).read_text()) for p in args.files]
    reference = records[0]["chunks"][min(records[0]["chunks"], key=int)]["texts"]
    report = {"files": args.files, "differing": {}}
    for path, value in zip(args.files, records):
        for chunk, item in value["chunks"].items():
            differ = [
                (condition, i)
                for condition, texts in item["texts"].items()
                for i, (digest, _) in enumerate(texts)
                if digest != reference[condition][i][0]
            ]
            report["differing"][f"{value['gpu']} chunk {chunk}"] = len(differ)
    report["allEqual"] = not any(report["differing"].values())
    print(json.dumps(report, indent=1))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    r = commands.add_parser("run")
    r.add_argument("model")
    r.add_argument("dataset")
    r.add_argument("out")
    r.add_argument("--rows", type=int, default=128)
    r.add_argument("--chunks", default="16,64,128")
    r.add_argument("--candidates", type=int, default=4)
    r.add_argument("--max-new-tokens", type=int, default=256)
    c = commands.add_parser("compare")
    c.add_argument("files", nargs="+")
    args = parser.parse_args()
    run(args) if args.command == "run" else compare(args)


if __name__ == "__main__":
    main()
