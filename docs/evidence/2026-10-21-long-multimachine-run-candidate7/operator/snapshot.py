"""Read-only view of the managed run on the coordinator (Thao WSL): progress, audits, members, active leases."""
import json, sqlite3, sys, time
from pathlib import Path

run = Path.home() / ".local/share/heteroes-c4-cpu/agent-state/runs" / sys.argv[1]
watch = sys.argv[2].split(",")
out = {"t": time.time()}
for name in ("state", "runner"):
    p = run / (name + ".json")
    if p.exists():
        out[name] = json.loads(p.read_text())
p = run / "ledger.sqlite"
if p.exists():
    with sqlite3.connect(f"file:{p}?mode=ro", uri=True) as d:
        out["applied"] = d.execute("select count(*) from generation_update where applied_at is not null").fetchone()[0]
        out["workers"] = dict(d.execute(
            "select a.worker_id,count(*) from result r join attempt a using(candidate_id,attempt_number) group by a.worker_id"))
        out["audits"] = d.execute("select count(*),coalesce(sum(matched=0),0) from audit").fetchone()
        out["quarantines"] = d.execute("select worker_id,reason from quarantine").fetchall()
        out["membership"] = d.execute("select worker_id,action,effective_generation from membership order by rowid").fetchall()
        out["expired"] = d.execute(
            "select a.worker_id,count(*) from expiry e join attempt a using(candidate_id,attempt_number) group by a.worker_id").fetchall()
        out["active"] = {
            w: d.execute(
                "select c.candidate_id,c.generation,a.attempt_number from candidate c join attempt a using(candidate_id) "
                "left join result r using(candidate_id) where a.worker_id=? and a.ended_at is null and a.deadline>? "
                "and r.candidate_id is null", (w, time.time())).fetchall()
            for w in watch
        }
print(json.dumps(out))
