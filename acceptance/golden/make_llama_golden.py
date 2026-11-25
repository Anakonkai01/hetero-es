#!/usr/bin/env python3
"""Build strict-b22-llama32.json from a `strict_parity.py --record` receipt of unsloth/Llama-3.2-1B-Instruct.

Unlike strict-b22.json (sealed after three hosts agreed), this golden starts from ONE host: the receipt names it. It
becomes cross-GPU evidence only when another GPU type passes the ordinary comparison run against it (PARITY OK).

    python3 acceptance/golden/make_llama_golden.py <recorded parity.json> > acceptance/golden/strict-b22-llama32.json
"""

import hashlib
import json
from pathlib import Path
import sys

path = Path(sys.argv[1])
receipt = json.loads(path.read_text())
assert receipt["status"] == "recorded" and receipt["model"] == "llama32" and not receipt["mismatches"]
assert all(c["restoreExact"] for c in receipt["cases"])
entry = {
    key: receipt[key] for key in ("modelFiles", "parentSha256", "schemaHash", "chatWorkload", "chatWorkloadSha256")
}
entry["noiseEngine"], entry["seed"], entry["sigma"] = "pcg64_u32_to_f16_normal_quantile_v2", 7001, 0.001
entry["cases"] = [{key: case[key] for key in ("state", "weightsSha256", "results")} for case in receipt["cases"]]
entry["eos"] = {k: receipt["eos"][k] for k in ("eosTokenIds", "maxNewTokens", "tokensSha256", "rowsEndingEarly")}
entry["recordedOn"] = receipt["environment"]
entry["source"] = {"receipt": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
print(json.dumps({"format": "heteroes-strict-parity-golden-v1", "models": {"llama32": entry}}, indent=1))
