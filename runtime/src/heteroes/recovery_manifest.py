"""Recovery object metadata shared by the CPU lab and numerical runtime."""

import json
import re

HEX = re.compile(r"[a-f0-9]{64}")
UUID = re.compile(r"[a-f0-9]{32}")
BASE_FILES = {"ledger.sqlite", "config.json", "identity.json"}


def safe_name(name, version=1):
    if not isinstance(name, str):
        return False
    if name in BASE_FILES:
        return True
    if re.fullmatch(r"weights/[a-f0-9]{64}\.bin", name):
        return True
    return version == 2 and (
        name in {"v3-state.json", "initial-adapter.bin", "usage.sqlite"}
        or bool(re.fullmatch(r"selection/[a-f0-9]{64}\.bin", name))
        or bool(re.fullmatch(r"[a-f0-9]{64}\.jsonl", name))
    )


def validate_manifest(m):
    if (
        not isinstance(m, dict)
        or type(m.get("formatVersion")) is not int
        or m["formatVersion"] not in (1, 2)
        or any(not isinstance(m.get(k), str) or not UUID.fullmatch(m[k]) for k in ("pointId", "runId"))
    ):
        raise ValueError("Invalid recovery identity")
    if type(m.get("generation")) is not int or m["generation"] < 0 or type(m.get("final")) is not bool:
        raise ValueError("Invalid generation")
    files = m.get("files")
    required = BASE_FILES | ({"v3-state.json"} if m["formatVersion"] == 2 else set())
    if (
        not isinstance(files, dict)
        or not required <= files.keys()
        or not 4 <= len(files) <= (12 if m["formatVersion"] == 2 else 5)
    ):
        raise ValueError("Incomplete recovery manifest")
    for name, meta in files.items():
        if not safe_name(name, m["formatVersion"]):
            raise ValueError("Unsafe recovery path")
        if (
            not isinstance(meta, dict)
            or not isinstance(meta.get("sha256"), str)
            or not HEX.fullmatch(meta["sha256"])
            or type(meta.get("sizeBytes")) is not int
            or not 0 < meta["sizeBytes"] <= (100_000_000 if name == "v3-state.json" else 5_000_000_000)
        ):
            raise ValueError("Invalid recovery object")
        if name.startswith(("weights/", "selection/")) and name.rsplit("/", 1)[1][:-4] != meta["sha256"]:
            raise ValueError("Weights name disagrees with checksum")
    for key in ("childWeightsSha256", "parentWeightsSha256"):
        if not isinstance(m.get(key), str) or not HEX.fullmatch(m[key]) or f"weights/{m[key]}.bin" not in files:
            raise ValueError("Missing canonical weights")
    if len(json.dumps(m)) > 32768:
        raise ValueError("Manifest is too large")
