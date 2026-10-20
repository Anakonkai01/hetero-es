"""Non-numerical usage receipts beside a run's canonical ledger. No numerical identity includes these timings."""

from contextlib import contextmanager
import json
import math
import os
from pathlib import Path
import sqlite3


def generated_token_count(tokens, eos_ids):
    for index, token in enumerate(tokens):
        if int(token) in eos_ids:
            return index + 1
    return len(tokens)


def validate_usage(value, count=None):
    if not isinstance(value, dict) or set(value) != {"formatVersion", "generatedTokens", "device", "wallSeconds"}:
        raise ValueError("Usage needs a version, generated token counts, device and wall seconds")
    counts, seconds = value["generatedTokens"], value["wallSeconds"]
    if (
        type(value["formatVersion"]) is not int
        or value["formatVersion"] != 1
        or value["device"] not in ("cpu", "cuda")
        or not isinstance(counts, list)
        or not counts
        or (count is not None and len(counts) != count)
        or any(type(n) is not int or not 0 <= n <= 10_000_000 for n in counts)
        or type(seconds) not in (int, float)
        or not math.isfinite(seconds)
        or not 0 <= seconds <= 10_000_000
    ):
        raise ValueError("Invalid usage counts, device or elapsed time")
    return {**value, "generatedTokens": list(counts)}


class CompletionBatch(tuple):
    def __new__(cls, texts, usage):
        value = super().__new__(cls, texts)
        value.usage = validate_usage(usage, len(value))
        return value


class UsageTexts(list):
    def __init__(self, texts, usage):
        super().__init__(texts)
        self.usage = validate_usage(usage, len(self))


class UsageStore:
    def __init__(self, path, *, create=True):
        self.path = Path(path)
        if self.path.is_symlink():
            raise ValueError("Usage database must not be a symlink")
        if create:
            self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            if not self.path.exists():
                descriptor = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                os.close(descriptor)
            with self.connection(write=True) as db:
                db.execute(
                    "CREATE TABLE IF NOT EXISTS usage (candidate_id TEXT, generation INTEGER, attempt INTEGER, "
                    "worker_id TEXT, kind TEXT, body TEXT, PRIMARY KEY(candidate_id,attempt,worker_id,kind))"
                )
                db.execute(
                    "CREATE TABLE IF NOT EXISTS coordinator_update (generation INTEGER PRIMARY KEY, gpu_seconds REAL)"
                )

    @contextmanager
    def connection(self, *, write=False):
        db = sqlite3.connect(
            str(self.path) if write else self.path.resolve().as_uri() + "?mode=ro", uri=not write, timeout=10
        )
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def record(self, descriptor, attempt, worker, usage, kind="candidate"):
        value = validate_usage(usage)
        if kind not in ("candidate", "audit") or type(attempt) is not int or attempt < 1 or not worker:
            raise ValueError("Invalid usage execution identity")
        body = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
        key = (descriptor.candidate_id, attempt, worker, kind)
        with self.connection(write=True) as db:
            db.execute("BEGIN IMMEDIATE")
            old = db.execute(
                "SELECT body FROM usage WHERE candidate_id=? AND attempt=? AND worker_id=? AND kind=?", key
            ).fetchone()
            if old is not None and old[0] != body:
                raise ValueError("Usage receipt changed on retry")
            db.execute(
                "INSERT OR IGNORE INTO usage VALUES (?,?,?,?,?,?)",
                (descriptor.candidate_id, descriptor.generation, attempt, worker, kind, body),
            )

    def record_update(self, generation, gpu_seconds):
        if (
            type(generation) is not int
            or generation < 0
            or type(gpu_seconds) not in (int, float)
            or not math.isfinite(gpu_seconds)
            or gpu_seconds < 0
        ):
            raise ValueError("Invalid coordinator update usage")
        with self.connection(write=True) as db:
            db.execute("INSERT OR IGNORE INTO coordinator_update VALUES (?,?)", (generation, gpu_seconds))

    def candidates(self):
        with self.connection() as db:
            return {
                row["candidate_id"]: validate_usage(json.loads(row["body"]))
                for row in db.execute("SELECT candidate_id,body FROM usage WHERE kind='candidate'")
            }

    def summary(self, generation=None, *, expected_candidates=0, expected_audits=0, expected_updates=0):
        where, parameters = ("", ()) if generation is None else (" WHERE generation=?", (generation,))
        with self.connection() as db:
            rows = db.execute("SELECT kind,body FROM usage" + where, parameters).fetchall()
            updates = db.execute("SELECT gpu_seconds FROM coordinator_update" + where, parameters).fetchall()
        counts = {"candidate": 0, "audit": 0}
        tokens = {"candidate": 0, "audit": 0}
        wall = gpu = 0.0
        for row in rows:
            value = validate_usage(json.loads(row["body"]))
            kind = row["kind"]
            counts[kind] += 1
            tokens[kind] += sum(value["generatedTokens"])
            wall += value["wallSeconds"]
            gpu += value["wallSeconds"] if value["device"] == "cuda" else 0
        update_seconds = sum(row[0] for row in updates)
        return {
            "generatedTokens": tokens["candidate"],
            "auditGeneratedTokens": tokens["audit"],
            "workerWallSeconds": wall,
            "workerGpuSeconds": gpu,
            "coordinatorUpdateGpuSeconds": update_seconds,
            "gpuSeconds": gpu + update_seconds,
            "reportedCandidates": counts["candidate"],
            "reportedAudits": counts["audit"],
            "recordedUpdates": len(updates),
            "partial": counts["candidate"] < expected_candidates
            or counts["audit"] < expected_audits
            or len(updates) < expected_updates,
            "scope": "successful worker executions and coordinator updates",
        }
