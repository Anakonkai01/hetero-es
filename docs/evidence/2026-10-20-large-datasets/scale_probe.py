"""Build, open and sample a file-backed Recipe v3 dataset from a generated JSON Lines file (CPU only).

python -I scale_probe.py --source runtime/src --rows 10000000 --work <empty folder on a large disk> --out result.json
"""

import argparse
import json
from pathlib import Path
import resource
import sys
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--rows", type=int, required=True)
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    sys.path.insert(0, str(args.source.resolve()))
    from heteroes.v3 import data

    args.work.mkdir(parents=True, exist_ok=False)
    source = args.work / "rows.jsonl"
    started = time.perf_counter()
    with source.open("w") as stream:
        for i in range(args.rows):
            stream.write(json.dumps({"question": f"Row {i}: what is {i % 977} times {i % 89}? Explain step by step.",
                                     "answer": str((i % 977) * (i % 89)), "level": i % 5, "tag": "gen"}) + "\n")  # fmt: skip
    timings = {"generate": time.perf_counter() - started}
    started = time.perf_counter()
    document = data.build_file_dataset({"all": (source, "jsonl")}, args.work / "dataset", prompt_field="question",
                                       max_bytes=2_000_000_000, max_rows=args.rows)  # fmt: skip
    timings["build"] = time.perf_counter() - started
    started = time.perf_counter()
    dataset = data.open_dataset(args.work / "dataset" / "dataset.json")
    timings["openAndVerify"] = time.perf_counter() - started
    started = time.perf_counter()
    batches = [data.batch(dataset, g, 32, 11) for g in range(3)]
    timings["firstThreeBatches"] = time.perf_counter() - started
    started = time.perf_counter()
    data.batch(dataset, 0, 32, 11, "epoch-shuffle@1")
    timings["epochShuffleBatch"] = time.perf_counter() - started
    result = {
        "rows": args.rows,
        "sourceBytes": source.stat().st_size,
        "document": document,
        "documentBytes": (args.work / "dataset" / "dataset.json").stat().st_size,
        "seconds": timings,
        "maxResidentMegabytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024,
        "batchHashes": [b["hash"] for b in batches],
    }
    args.out.write_text(json.dumps(result, indent=1) + "\n")
    print(json.dumps({k: result[k] for k in ("rows", "sourceBytes", "seconds", "maxResidentMegabytes")}))


if __name__ == "__main__":
    main()
