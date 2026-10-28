"""The device agent's wire protocol: command kinds, lab requests, public error reasons and bounded snapshots."""

import json
import re
import urllib.error
import urllib.request

from heteroes.http_transport import USER_AGENT


COMMAND_KINDS = frozenset(
    {
        "SET_CONTRIBUTION",
        "COORDINATE",
        "START_WORKER",
        "STOP_WORKER",
        "CANCEL_ASSIGNMENT",
        "UPDATE_BACKUP_POLICY",
        "UPDATE_MEMBERSHIP",
        "RETRY_WORKER",
        "PAUSE_ASSIGNMENT",
        "QUALIFY_MODEL",
        "CANCEL_MODEL_QUALIFICATION",
    }
)


def membership_change(change):
    """A lab request to add or remove a worker of a running experiment (ADR-009), or InvalidCommand: it can never succeed."""
    if not isinstance(change, dict):
        raise InvalidCommand("Invalid membership change")
    allowed = {"changeId", "workerId", "action", "actor", "grant"}
    texts = ("changeId", "workerId", "actor")
    if (
        set(change) - allowed
        or not set(texts) <= set(change)
        or any(not isinstance(change[key], str) or not change[key] or len(change[key]) > 200 for key in texts)
        or change.get("action") not in ("JOIN", "LEAVE")
    ):
        raise InvalidCommand("Invalid membership change")
    grant = change.get("grant")
    if change["action"] == "JOIN" and (not isinstance(grant, str) or not grant):
        raise InvalidCommand("A joining worker needs its compute credential")
    return {key: change[key] for key in texts + ("action",)} | ({"grant": grant} if change["action"] == "JOIN" else {})


def request(url, path, token, body, method=None):
    req = urllib.request.Request(
        url.rstrip("/") + path,
        data=None if body is None else json.dumps(body, allow_nan=False).encode(),
        method=method,
        headers={
            "Authorization": "Bearer " + token,
            "Content-Type": "application/json",
            "User-Agent": USER_AGENT,
            **({"X-HeteroES-Agent-Commands": ",".join(sorted(COMMAND_KINDS))} if path == "/api/v1/device/poll" else {}),
        },
    )
    # Never expose exception URLs, token-bearing bodies or server tracebacks.
    with urllib.request.urlopen(req, timeout=15) as response:
        return json.load(response)


def reachable(url, token, timeout=4):
    """True if a coordinator answers /v1/health with this grant. No proxy, like the worker's own client."""
    try:
        req = urllib.request.Request(
            url.rstrip("/") + "/v1/health", headers={"Authorization": "Bearer " + token, "User-Agent": USER_AGENT}
        )
        with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req, timeout=timeout) as response:
            return response.status == 200 and json.load(response).get("ok") is True
    except Exception:
        return False


class InvalidCommand(ValueError):
    """Unknown kind or malformed identity: retrying can never succeed, so it is acknowledged."""


# The counter table of each event the agent raises about a command that did not finish.
PROBLEM_TABLES = {"agent_command_failed": "command_failures", "agent_command_deferred": "command_deferrals"}


def public_reason(error):
    """The agent's own words for the lab, at most 200 characters. Only the agent's own error types are described:
    a network or OS error may carry a grant URL or a private path. URLs are masked in any case."""
    if type(error) not in (ValueError, RuntimeError, InvalidCommand):
        return None
    return re.sub(r"\b[a-z][a-z0-9+.-]*://\S+", "<url>", str(error))[:200]


def max_chunk(config):
    """The largest evaluation chunk this device offers a recipe that allows several (ADR-010): the owner's limit, or one
    from its memory (a larger chunk that does not fit falls back to the recipe's own, CandidateExecutor)."""
    if config.get("maxChunk"):
        return int(config["maxChunk"])
    vram = (config.get("selfTest") or {}).get("vramTotalMb") or 0
    return 64 if vram >= 14_000 else 32 if vram >= 8_000 else 16


def bounded_snapshot(snapshot, max_bytes=1_250_000):
    """Bound heartbeat detail while preserving final state and global counters.

    Complete events are spooled separately before this projection is reduced.
    Full candidate history remains in the canonical ledger/recovery points.
    """
    generations = snapshot["generations"]
    snapshot["completedGenerationCount"] = sum(g["status"] == "COMPLETED" for g in generations)
    snapshot["latestGeneration"] = generations[-1] if generations else None

    def size():
        return len(json.dumps(snapshot, allow_nan=False).encode())

    def halve(key, limit=None):
        def over():
            if limit is None:
                return size() > max_bytes
            return size() > max_bytes and len(json.dumps(snapshot[key], allow_nan=False).encode()) > limit

        while snapshot[key] and over():
            snapshot[key] = snapshot[key][max(1, len(snapshot[key]) // 2) :]
            snapshot["monitoringPartial"] = True

    if size() <= max_bytes:
        return snapshot
    # lifecycle, coordinator and worker logs are concatenated: order them so the newest survive
    snapshot["events"].sort(key=lambda e: e.get("t") if isinstance(e.get("t"), (int, float)) else 0)
    halve("events", limit=max_bytes // 4)  # a quarter for the newest events; the rest only as a last resort
    # copies of whole log files are a download convenience: they go before any live work
    while snapshot.get("artifactContents") and size() > max_bytes:
        largest = max(snapshot["artifactContents"], key=lambda k: len(snapshot["artifactContents"][k]["base64"]))
        del snapshot["artifactContents"][largest]
        snapshot["monitoringPartial"] = True

    # attempts and candidates go by generation, oldest first and together, so the live view keeps the newest
    # generations whole (halving attempts alone once left a long run with candidates but no attempt: finding 10)
    def generation(item):
        match = re.search(r"\.g(\d+)$", str(item.get("generationId")))
        return int(match.group(1)) if match else -1

    excess = size() - max_bytes
    if excess > 0:
        weight = {}
        for key in ("attempts", "candidates"):
            for item in snapshot[key]:
                g = generation(item)
                weight[g] = weight.get(g, 0) + len(json.dumps(item, allow_nan=False).encode()) + 1
        dropped = set()
        for g in sorted(weight)[:-1]:  # never the newest one here; the halving below is the last resort
            if excess <= 0:
                break
            dropped.add(g)
            excess -= weight[g]
        if dropped:
            for key in ("attempts", "candidates"):
                snapshot[key] = [item for item in snapshot[key] if generation(item) not in dropped]
            snapshot["monitoringPartial"] = True
    for key in ("events", "attempts", "candidates", "generations"):
        halve(key)
    if size() > max_bytes:
        raise ValueError("Runtime state exceeds the monitoring budget")
    return snapshot
