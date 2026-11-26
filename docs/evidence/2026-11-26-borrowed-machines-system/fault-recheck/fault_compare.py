"""Per-generation durations, audit closures and membership changes of fault-demo runs (coordinator events)."""
import collections, json, sys
from pathlib import Path
RUNS = Path.home() / ".local/share/heteroes-worker/agent-state/runs"
out = {}
for run in sys.argv[1:]:
    root = next(RUNS.glob(run + "*"))
    ev = [json.loads(l) for l in (root / "events.jsonl").read_text().splitlines() if l.strip()]
    t = lambda e: e.get("t") or e.get("time") or e.get("ts")
    opens = {e["generation"]: t(e) for e in ev if e.get("event", e.get("type")) == "generation_open"}
    gens = sorted(opens)
    dur = {g: round(opens[g + 1] - opens[g], 1) for g in gens if g + 1 in opens}
    reasons = collections.Counter(e.get("reason") for e in ev if e.get("event", e.get("type")) == "audit_incomplete")
    per_gen_reason = collections.defaultdict(list)
    for e in ev:
        if e.get("event", e.get("type")) == "audit_incomplete":
            per_gen_reason[e.get("generation")].append(e.get("reason"))
    members = [(e.get("generation"), e.get("change") or e.get("kind") or e.get("action")) for e in ev if e.get("event", e.get("type")) == "membership_changed"]
    kinds = collections.Counter(e.get("event", e.get("type")) for e in ev)
    out[run] = {"durations": dur, "auditIncomplete": dict(reasons), "perGeneration": dict(per_gen_reason), "membership": members,
                "audits": {k: v for k, v in kinds.items() if "audit" in str(k)}}
print(json.dumps(out, indent=1, ensure_ascii=False))
