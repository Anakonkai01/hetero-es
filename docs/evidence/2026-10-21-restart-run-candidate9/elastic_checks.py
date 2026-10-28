"""The candidate8 elastic checks (ADR-009 items 1-8) on a private ledger copy; used by verify-records.py and tested
against tampered scratch copies (negative controls)."""
import json
import sqlite3
from pathlib import Path
from heteroes.ledger import Ledger
from heteroes.product.membership import membership_violations


def elastic_checks(root, experiment, generations, population, joiner_id, joiner_changes, expiry_workers, restart_workers,
                   lifecycle):
    with Ledger(Path(root) / 'ledger.sqlite') as ledger, sqlite3.connect(f'file:{Path(root) / "ledger.sqlite"}?mode=ro', uri=True) as db:
        violations = membership_violations(ledger, experiment)
        changes = [(c.worker_id, c.action, c.effective_generation) for c in ledger.list_membership(experiment)]
        joiner = [c for c in changes if c[0] == joiner_id]
        expected = joiner_changes.split(',')
        increasing = all(x[2] < y[2] for x, y in zip(joiner, joiner[1:]))
        windows = [(joiner[i][2], joiner[i + 1][2] if i + 1 < len(joiner) else 10**9) for i in range(0, len(joiner), 2)]
        commits = sorted({g for g, _, w in ledger.list_committed_attempts(experiment) if w == joiner_id})
        in_window = all(any(lo <= g < hi for lo, hi in windows) for g in commits)
        each_window = all(any(lo <= g < hi for g in commits) for lo, hi in windows)
        expiry = {}
        for worker in expiry_workers.split(','):
            rows = [e for e in ledger.list_expired(experiment) if e[2] == worker]
            fenced = [db.execute('select count(*) from result where candidate_id=? and attempt_number=?', (e[0], e[1])).fetchone()[0] == 0 for e in rows]
            retried = [db.execute('select attempt_number from result where candidate_id=?', (e[0],)).fetchone() for e in rows]
            expiry[worker] = {'expiries': [{'candidateId': e[0], 'attempt': e[1], 'retriedBy': r[0] if r else None} for e, r in zip(rows, retried)],
                              'ok': bool(rows) and all(fenced) and all(r is not None and r[0] > e[1] for e, r in zip(rows, retried))}
        events = [json.loads(x) for x in Path(lifecycle).read_text().splitlines() if x.strip()]
        restarts = {}
        for worker in restart_workers.split(','):
            started = [e for e in events if e.get('event') == 'worker_restarted' and e.get('worker_id') == worker and e.get('launch', 0) >= 1]
            after = [db.execute('select count(*) from result r join attempt t using(candidate_id,attempt_number) where t.worker_id=? and t.leased_at>=?', (worker, e['t'])).fetchone()[0] for e in started]
            manual = [c for c in changes if c[0] == worker and not (c[1] == 'JOIN' and c[2] == 0)]
            restarts[worker] = {'launches': [e['launch'] for e in started], 'resultsAfterRestart': after, 'manualMembershipChanges': manual,
                                'ok': bool(started) and max(after) > 0 and not manual}
        total = db.execute('select count(*),count(distinct candidate_id) from result').fetchone()
    elastic = {'membershipViolations': violations, 'membershipChanges': changes, 'joinerWindows': windows, 'joinerCommitGenerations': commits,
               'expiry': expiry, 'restarts': restarts, 'results': {'rows': total[0], 'distinctCandidates': total[1], 'expected': generations * population}}
    elastic['ok'] = (violations == [] and [c[1] for c in joiner] == expected and increasing and in_window and each_window
                     and all(v['ok'] for v in expiry.values()) and all(v['ok'] for v in restarts.values())
                     and total[0] == total[1] == generations * population)
    return elastic
