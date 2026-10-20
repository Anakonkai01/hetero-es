"""Export only numerical evidence from two completed ledgers; lease/device secrets stay in private source files."""

import argparse
import json
from pathlib import Path

from heteroes.canonical import canonical_json_hash
from heteroes.ledger import Ledger


def read(path):
    rows = []
    with Ledger(path) as ledger:
        for generation in (0, 1):
            candidates = ledger.list_candidates("local", generation)
            update = ledger.get_update("local", generation)
            rows.append({
                "generation": generation,
                "recordHash": update.record.hash,
                "childSha256": update.child_weights_sha256,
                "candidates": [{"candidateId": c.descriptor.candidate_id,
                                "seed": c.descriptor.seed, "sign": c.descriptor.sign,
                                "reward": c.result.reward,
                                "texts": ledger.get_completions(c.descriptor.candidate_id)} for c in candidates],
            })
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("baseline", type=Path)
    parser.add_argument("windows", type=Path)
    parser.add_argument("worker_events", type=Path)
    parser.add_argument("out", type=Path)
    args = parser.parse_args()
    baseline, windows = read(args.baseline), read(args.windows)
    assert baseline == windows, "Numerical records, candidate texts or rewards differ"
    events = [json.loads(line) for line in args.worker_events.read_text().splitlines()]
    replay = [{key: event.get(key) for key in ("from_sha256", "to_sha256", "verified", "unverified_coefficients")}
              for event in events if event["event"] == "replay"]
    stopped = [event["reason"] for event in events if event["event"] == "exit"]
    assert stopped == ["finished"]
    result = {"equalRecordsTextsRewardsAndWeights": True, "baseline": "5070 Ti coordinator + local GPU worker",
              "distributed": "native Windows RTX 3060 coordinator + Quang RTX 3060 WSL worker",
              "generations": windows, "workerReplays": replay, "workerExit": stopped[0],
              "numericalReceiptHash": canonical_json_hash(windows),
              "auditsEnabled": False}
    with args.out.open("x") as stream:
        json.dump(result, stream, indent=1)
        stream.write("\n")
    print("Both generation records, all candidate texts/rewards and both child weights match exactly")


if __name__ == "__main__":
    main()
