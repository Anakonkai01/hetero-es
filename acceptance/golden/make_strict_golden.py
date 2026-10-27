#!/usr/bin/env python3
"""Build strict-b22.json from the sealed trained-parity receipts of runtime 0eb86cb9 (hashes only, no token lists).

Those receipts agree on the 5070 Ti, the 3060 under WSL2 and (Qwen) native Windows: see
docs/evidence/2026-10-27-strict-combined-acceptance (verify.py, summary-01.json).

    python3 acceptance/golden/make_strict_golden.py > acceptance/golden/strict-b22.json
"""

import hashlib
import json
from pathlib import Path

RAW = Path("docs/evidence/2026-10-27-strict-combined-acceptance/raw")
models = {}
for name in ("qwen", "smol", "tiny"):
    receipt = json.loads((RAW / f"{name}-parity-5070ti-01.json").read_text())
    assert receipt["status"] == "ok" and all(c["restoreExact"] and c["tileEqualsStream"] for c in receipt["cases"])
    entry = {key: receipt[key] for key in ("modelFiles", "parentSha256", "schemaHash", "noiseEngine", "seed", "sigma")}
    if "chatWorkloadSha256" in receipt:
        entry["chatWorkloadSha256"] = receipt["chatWorkloadSha256"]
    entry["cases"] = [
        {
            "state": case["state"],
            "weightsSha256": case["weightsSha256"],
            "results": {
                schedule: {
                    label: (
                        value if label == "prefillLogitsSha256" else {k: value[k] for k in ("tokensSha256", "rewards")}
                    )
                    for label, value in result.items()
                }
                for schedule, result in case["results"].items()
            },
        }
        for case in receipt["cases"]
    ]
    if "eosCheck" in receipt:
        eos = receipt["eosCheck"]
        assert eos["equal"] and eos["captured"]["tokensSha256"] == eos["uncaptured"]["tokensSha256"]
        entry["eos"] = {
            "eosTokenIds": eos["eosTokenIds"],
            "maxNewTokens": eos["maxNewTokens"],
            "tokensSha256": eos["captured"]["tokensSha256"],
            "rowsEndingEarly": eos["rowsEndingEarly"],
        }
    entry["source"] = {
        "receipt": str(RAW / f"{name}-parity-5070ti-01.json"),
        "sha256": hashlib.sha256((RAW / f"{name}-parity-5070ti-01.json").read_bytes()).hexdigest(),
    }
    models[name] = entry
print(
    json.dumps(
        {
            "format": "heteroes-strict-parity-golden-v1",
            "runtime": "0eb86cb948878fe430049882b80b3a5ad74730ba",
            "models": models,
        },
        indent=1,
    )
)
