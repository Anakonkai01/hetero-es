"""Inject declared faults into one running lab run at generation thresholds and log every action (no credentials).

    PYTHONPATH=runtime/src python fault.py RUN_ID OUT.jsonl
"""
import json, subprocess, sys, time
from heteroes.sdk_lab import Lab

run_id, out = sys.argv[1], sys.argv[2]
lab = Lab.from_session()
NHUT = 'heheboiz@100.108.195.50'
WIN = 'thao_nguyen@100.92.20.58'
PS = '/home/pc5070ti/projects/heteroes/.scratch/candidate14/run-windows-ps.py'
UIA = '/home/pc5070ti/projects/heteroes/.scratch/candidate14e/uia-enable.ps1'
RELAUNCH = '/home/pc5070ti/projects/heteroes/.scratch/overnight/win-relaunch.ps1'

def log(**kw):
    kw['t'] = time.time(); kw['iso'] = time.strftime('%H:%M:%S')
    with open(out, 'a') as f: f.write(json.dumps(kw) + '\n')
    print(json.dumps(kw), flush=True)

def sh(argv, timeout=180):
    r = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
    return r.returncode, (r.stdout + r.stderr)[-1500:]

KILL_WORKER = r'''python3 - <<'PY'
import json, os, signal, pathlib
best = None
for p in pathlib.Path.home().glob('.local/share/heteroes-worker/agent-state/workers/*/process.json'):
    pid = json.loads(p.read_text()).get('pid')
    try: cmd = open(f'/proc/{pid}/cmdline', 'rb').read().decode(errors='replace')
    except OSError: continue
    if 'heteroes' in cmd and (best is None or p.stat().st_mtime > best[0]): best = (p.stat().st_mtime, pid, cmd[:120])
if best:
    os.kill(best[1], signal.SIGKILL); print('killed', best[1], best[2].replace('\x00', ' '))
else: print('no live worker process found')
PY'''
CUT = "echo 123 | sudo -S -p '' iptables -I OUTPUT 1 -m owner --uid-owner 1000 -m conntrack --ctstate NEW -p tcp ! --dport 22 -j REJECT -m comment --comment heteroes-fault"
HEAL = "echo 123 | sudo -S -p '' iptables -D OUTPUT -m owner --uid-owner 1000 -m conntrack --ctstate NEW -p tcp ! --dport 22 -j REJECT -m comment --comment heteroes-fault; echo 123 | sudo -S -p '' iptables -S OUTPUT | grep -c heteroes-fault"

plan = [
    (6, 'kill-nhut-worker', lambda: sh(['ssh', '-o', 'BatchMode=yes', NHUT, KILL_WORKER])),
    (14, 'cut-nhut-network-180s', None),
    (24, 'reboot-nhut', lambda: sh(['ssh', '-o', 'BatchMode=yes', NHUT, "echo 123 | sudo -S -p '' systemctl reboot"], 30)),
    (34, 'kill-windows-app', None),
]
done = set()
log(event='fault_driver_start', runId=run_id, plan=[(g, n) for g, n, _ in plan])
while True:
    try:
        e = lab.run(run_id).experiment()
    except Exception as error:
        log(event='lab_read_failed', error=type(error).__name__); time.sleep(15); continue
    status, gen = e['status'], e.get('completedGenerations') or 0
    if status in ('COMPLETED', 'FAILED', 'CANCELLED'):
        log(event='run_end', status=status, completedGenerations=gen); break
    for threshold, name, action in plan:
        if gen >= threshold and name not in done:
            done.add(name)
            log(event='fault_begin', name=name, generation=gen)
            try:
                if name == 'cut-nhut-network-180s':
                    rc, text = sh(['ssh', '-o', 'BatchMode=yes', NHUT, CUT]); log(event='fault_step', name=name, step='cut', rc=rc, out=text)
                    time.sleep(180)
                    rc, text = sh(['ssh', '-o', 'BatchMode=yes', NHUT, HEAL]); log(event='fault_step', name=name, step='heal', rc=rc, out=text)
                elif name == 'kill-windows-app':
                    rc, text = sh(['ssh', '-o', 'BatchMode=yes', WIN, '/mnt/c/Windows/System32/taskkill.exe /F /IM "HeteroES Worker.exe" /T'])
                    log(event='fault_step', name=name, step='taskkill', rc=rc, out=text)
                    time.sleep(60)
                    rc, text = sh(['python3', PS, RELAUNCH], 240); log(event='fault_step', name=name, step='relaunch', rc=rc, out=text)
                    rc, text = sh(['python3', PS, UIA], 240); log(event='fault_step', name=name, step='switch-on', rc=rc, out=text)
                else:
                    rc, text = action(); log(event='fault_step', name=name, rc=rc, out=text)
            except Exception as error:
                log(event='fault_error', name=name, error=repr(error)[:500])
    time.sleep(10)
