"""Mutation check for the candidate9 monitor logic: every mutant of `decide` must make a test fail (scratch copy)."""

import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent
WORK = Path(sys.argv[1])
PY = str(Path.home() / "miniforge3/envs/heteroes-match/bin/python")
M = [
    ("if applied >= JOIN_AT and not", "if applied > JOIN_AT and not"),
    ('if flags.get("joined") and applied >= QUANG_AT', "if applied >= QUANG_AT"),
    (
        '        elif active.get(QUANG):\n            actions.append("fault_quang")',
        '        else:\n            actions.append("fault_quang")',
    ),
    ("        if applied >= QUANG_SKIP:", "        if False:"),
    ("    if quang_status(flags, snap, now) not in DONE:\n        return actions\n", ""),
    ('actions.append("skip_rejoin" if applied >= REJOIN_SKIP else "leave")', 'actions.append("leave")'),
    ("elif effective is not None and applied > effective:", "elif effective is not None:"),
    ("elif effective is not None and applied > effective:", "else:"),
    ("    if rejoin_status(flags, snap, now) not in DONE:\n        return actions\n", ""),
    (
        '        elif active.get(WIN):\n            actions.append("fault_win")',
        '        else:\n            actions.append("fault_win")',
    ),
    ("        if applied >= WIN_SKIP:", "        if False:"),
    ('now - flags["stoppedAt"] >= OUTAGE', 'now - flags["stoppedAt"] > OUTAGE * 2'),
    ('if flags.get("relaunched") and not flags.get("contributionOn"):', 'if flags.get("relaunched"):'),
    (
        'return restart_status(snap, WIN, flags["contributionOn"], flags["winBase"], now)',
        'return restart_status(snap, WIN, flags["stoppedAt"], flags["winBase"], now)',
    ),
    ('return "failed" if now - since >= RESTART_DEADLINE else "waiting"', 'return "waiting"'),
    ("    if restarted and produced:", "    if restarted or produced:"),
    ('e[0] == "worker_restarted" and e[1] == worker and e[3] >= since', "e[1] == worker and e[3] >= since"),
    ('e[0] == "worker_restarted" and e[1] == worker and e[3] >= since', 'e[0] == "worker_restarted" and e[3] >= since'),
    (
        'e[0] == "worker_restarted" and e[1] == worker and e[3] >= since',
        'e[0] == "worker_restarted" and e[1] == worker',
    ),
    ('snap.get("workers", {}).get(worker, 0) > base', 'snap.get("workers", {}).get(worker, 0) >= base'),
    ('if w == JOINER and action == "LEAVE"', "if w == JOINER"),
    (
        '    if status in TERMINAL:\n        return ["finish"]',
        '    if status in ("COMPLETED",):\n        return ["finish"]',
    ),
    ('and not flags.get("pauseRequested"):\n        return ["pause"]', ':\n        return ["pause"]'),
    ('(snap.get("audits", [0, 0])[1] or snap.get("quarantines"))', '(snap.get("audits", [0, 0])[1])'),
]
killed = 0
for i, (old, new) in enumerate(M, 1):
    if WORK.exists():
        shutil.rmtree(WORK)
    WORK.mkdir(parents=True)
    shutil.copy(HERE / "test_monitor.py", WORK / "test_monitor.py")
    text = (HERE / "monitor.py").read_text()
    assert text.count(old) == 1, (i, old)
    (WORK / "monitor.py").write_text(text.replace(old, new))
    r = subprocess.run(
        [PY, "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider", "test_monitor.py"],
        cwd=WORK,
        capture_output=True,
        text=True,
    )
    ok = r.returncode != 0
    killed += ok
    print(f"mutant {i:2d} {'KILLED' if ok else 'SURVIVED'}: {old.strip()[:70]!r}", flush=True)
print(f"{killed}/{len(M)} killed")
