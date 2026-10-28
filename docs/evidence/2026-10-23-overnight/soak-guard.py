"""Watch one run: pause it if nhan's root disk falls below 12 GiB; print one line and exit on the end or a bad event."""
import json, shutil, sys, time
from pathlib import Path
from heteroes.sdk_lab import Lab

run_id, log = sys.argv[1], Path(sys.argv[2])
root = Path.home() / '.local/share/heteroes-worker/agent-state/runs' / run_id
lab, paused = Lab.from_session(), False
BAD = ('worker_lost', 'worker_quarantined', 'worker_restart_limit', 'needs_private_route')

def note(**kw):
    kw['t'] = time.time(); kw['iso'] = time.strftime('%H:%M:%S')
    with log.open('a') as f: f.write(json.dumps(kw) + '\n')
    return kw

while True:
    free = shutil.disk_usage('/').free / 2**30
    try:
        status = json.loads((root / 'state.json').read_text())['status']
    except Exception:
        status = 'UNKNOWN'
    if status in ('COMPLETED', 'FAILED', 'CANCELLED', 'PAUSED'):
        print(json.dumps(note(event='end', status=status, freeGiB=round(free, 1)))); break
    if free < 12 and not paused:
        paused = True
        try:
            lab.request('POST', f'/api/v1/experiments/{run_id}/pause')
            print(json.dumps(note(event='paused_low_disk', freeGiB=round(free, 1)))); 
        except Exception as error:
            print(json.dumps(note(event='pause_failed', error=repr(error)[:200], freeGiB=round(free, 1))))
    text = (root / 'lifecycle.jsonl').read_text() if (root / 'lifecycle.jsonl').exists() else ''
    hits = [b for b in BAD if b in text]
    mism = '"matched": false' in (root / 'events.jsonl').read_text() if (root / 'events.jsonl').exists() else False
    if hits or mism:
        print(json.dumps(note(event='alert', hits=hits, mismatch=mism, status=status))); break
    time.sleep(60)
