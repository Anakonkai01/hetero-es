"""Negative and positive controls for elastic_checks.py, on scratch copies of a finished run's private ledger.

    PYTHONPATH=runtime/src python negative.py <private-run-copy> <experiment-id> <scratch-dir> <joiner> <win> <local>

The positive control uses a SYNTHETIC lifecycle line (the copy is a candidate7 run, which never restarted anyone): it
only shows that the checker passes when every property holds. Each negative control tampers one property and must FAIL.
"""
import json
import shutil
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from elastic_checks import elastic_checks

source, experiment, scratch, joiner, win, local = sys.argv[1:7]
scratch = Path(scratch)


def prepare(name, sql=None, lifecycle=None):
    target = scratch / name
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(source, target)
    (target / "ledger.sqlite-wal").unlink(missing_ok=True)
    (target / "ledger.sqlite-shm").unlink(missing_ok=True)
    db = sqlite3.connect(target / "ledger.sqlite")
    first = db.execute("select min(leased_at) from attempt where worker_id=?", (win,)).fetchone()[0]
    for statement in sql or []:
        db.execute(statement.format(joiner=joiner, win=win))
    db.commit()
    db.close()
    lines = lifecycle if lifecycle is not None else [{"event": "worker_restarted", "worker_id": win, "launch": 1, "t": first}]
    (target / "lifecycle.jsonl").write_text("".join(json.dumps(x) + "\n" for x in lines))
    return target


def run(target, changes="JOIN,LEAVE", expiry=None, restart=None):
    return elastic_checks(target, experiment, 50, 8, joiner, changes, expiry or win, restart or win, target / "lifecycle.jsonl")


GEN5 = ("update attempt set worker_id='{joiner}' where (candidate_id,attempt_number) in (select r.candidate_id,r.attempt_number "
        "from result r join candidate c using(candidate_id) where c.generation=5 order by c.candidate_index limit 1)")
COMMITTED = ("insert into expiry select candidate_id,attempt_number,0 from result r where (candidate_id,attempt_number) in "
             "(select r.candidate_id,r.attempt_number from result r join attempt a using(candidate_id,attempt_number) "
             "where a.worker_id='{win}' limit 1)")
cases = [
    ("positive-synthetic", prepare("positive"), {}, True),
    ("non-member-result", prepare("non-member", [GEN5]), {}, False),
    ("no-expiry-row", prepare("no-expiry", ["delete from expiry"]), {}, False),
    ("no-restart-event", prepare("no-restart", lifecycle=[]), {}, False),
    ("restart-without-new-results", prepare("late-restart", lifecycle=[{"event": "worker_restarted", "worker_id": win, "launch": 1, "t": 9e12}]), {}, False),
    ("restart-launch-0-only", prepare("launch0", lifecycle=[{"event": "worker_restarted", "worker_id": win, "launch": 0, "t": 1}]), {}, False),
    ("manual-membership-change-for-the-restarted-worker",
     prepare("manual", ["insert into membership select experiment_id,'x-leave','{win}','LEAVE',30,'op',0 from membership limit 1",
                        "insert into membership select experiment_id,'x-join','{win}','JOIN',31,'op',0 from membership limit 1"]), {}, False),
    ("expired-attempt-also-committed", prepare("stale", [COMMITTED]), {}, False),
    ("missing-result", prepare("missing", ["delete from result where candidate_id in (select candidate_id from result limit 1)"]), {}, False),
    ("joiner-sequence-differs-from-the-declared-one", prepare("sequence"), {"changes": "JOIN,LEAVE,JOIN"}, False),
]
failed = 0
for name, target, kwargs, expect_ok in cases:
    result = run(target, **kwargs)
    good = result["ok"] == expect_ok
    failed += not good
    why = {"violations": len(result["membershipViolations"]), "expiryOk": [v["ok"] for v in result["expiry"].values()],
           "restartOk": [v["ok"] for v in result["restarts"].values()], "results": result["results"]["rows"]}
    print(f"{'OK  ' if good else 'WRONG'} {name}: checker says ok={result['ok']} (expected {expect_ok}) {why}")
print("ALL CONTROLS BEHAVE" if not failed else f"{failed} CONTROL(S) WRONG")
raise SystemExit(1 if failed else 0)
