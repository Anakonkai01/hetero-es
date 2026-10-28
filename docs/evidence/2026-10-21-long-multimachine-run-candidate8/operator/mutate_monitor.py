"""Mutation check for the candidate8 monitor logic: every mutant of `decide` must make a test fail (scratch copy)."""
import shutil, subprocess, sys
from pathlib import Path

HERE = Path(__file__).parent
WORK = Path(sys.argv[1])
PY = str(Path.home() / "miniforge3/envs/heteroes-match/bin/python")
M = [
    ("applied >= JOIN1_AT and not", "applied > JOIN1_AT and not"),
    ("applied >= WIN_AT and not flags.get(\"stoppedAt\") and active.get(WIN)", "applied >= WIN_AT and not flags.get(\"stoppedAt\")"),
    ("now - flags[\"stoppedAt\"] >= OUTAGE", "now - flags[\"stoppedAt\"] > OUTAGE * 2"),
    ("if flags.get(\"relaunched\") and not flags.get(\"contributionOn\"):", "if flags.get(\"relaunched\"):"),
    ("applied >= LEAVE_AT and flags.get(\"joined\") and not flags.get(\"left\") and win_done", "applied >= LEAVE_AT and flags.get(\"joined\") and not flags.get(\"left\")"),
    ("applied >= LEAVE_AT and flags.get(\"joined\")", "applied >= LEAVE_AT"),
    ("if win_done and applied >= QUANG_AT", "if applied >= QUANG_AT"),
    ("        if active.get(QUANG):\n            actions.append(\"fault_quang\")", "        if True:\n            actions.append(\"fault_quang\")"),
    ("elif applied >= JOIN2_AT:", "elif applied >= 0:"),
    ("flags.get(\"left\") and not flags.get(\"joined2\")", "not flags.get(\"joined2\")"),
    ("and \"join2\" not in skipped and quang_done", "and \"join2\" not in skipped"),
    ("        elif active.get(LOCAL):\n            actions.append(\"sigstop\")", "        else:\n            actions.append(\"sigstop\")"),
    ("(waited >= STOP_SECONDS and expired) or waited >= STOP_MAX", "waited >= STOP_SECONDS"),
    ("(waited >= STOP_SECONDS and expired) or waited >= STOP_MAX", "(waited >= STOP_SECONDS and expired)"),
    ("return \"failed\" if now - since >= RESTART_DEADLINE else \"waiting\"", "return \"waiting\""),
    ("    if restarted and produced:", "    if restarted or produced:"),
    ("e[0] == \"worker_restarted\" and e[1] == worker and e[3] >= since", "e[0] == \"worker_restarted\" and e[1] == worker"),
    ("snap.get(\"workers\", {}).get(worker, 0) > base", "snap.get(\"workers\", {}).get(worker, 0) >= base"),
    ("    if status in TERMINAL:\n        return [\"finish\"]", "    if status in (\"COMPLETED\",):\n        return [\"finish\"]"),
    ("and not flags.get(\"pauseRequested\"):\n        return [\"pause\"]", ":\n        return [\"pause\"]"),
    ("(snap.get(\"audits\", [0, 0])[1] or snap.get(\"quarantines\"))", "(snap.get(\"audits\", [0, 0])[1])"),
]
killed = 0
for i, (old, new) in enumerate(M, 1):
    if WORK.exists():
        shutil.rmtree(WORK)
    WORK.mkdir(parents=True)
    for name in ("test_monitor.py",):
        shutil.copy(HERE / name, WORK / name)
    text = (HERE / "monitor.py").read_text()
    assert text.count(old) == 1, (i, old)
    (WORK / "monitor.py").write_text(text.replace(old, new))
    r = subprocess.run([PY, "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider", "test_monitor.py"], cwd=WORK,
                       capture_output=True, text=True)
    ok = r.returncode != 0
    killed += ok
    print(f"mutant {i:2d} {'KILLED' if ok else 'SURVIVED'}: {old.strip()[:70]!r}", flush=True)
print(f"{killed}/{len(M)} killed")
