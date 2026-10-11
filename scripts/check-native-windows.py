#!/usr/bin/env python3
"""Private native Windows acceptance. Default is read-only; GPU phases need two opt-ins."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import sqlite3
import sys
import time
import urllib.request

PRIVATE = Path.home() / '.config/heteroes-m3-campaign'
STATE = Path.home() / '.local/share/heteroes-m3-campaign'
API = 'http://100.110.165.40:8002/api/v1'
TERMINAL = {'COMPLETED', 'CANCELLED', 'FAILED'}
token = ''


def call(route, body=None):
    request = urllib.request.Request(API + route,
        data=json.dumps(body).encode() if body is not None else None,
        headers={'Content-Type': 'application/json', 'X-Workspace-Id': 'lab',
                 **({'Authorization': 'Bearer ' + token} if token else {})})
    with urllib.request.urlopen(request, timeout=15) as response:
        return json.load(response)


def write(name, body):
    STATE.mkdir(parents=True, exist_ok=True, mode=0o700)
    file = STATE / name
    file.write_text(json.dumps(body, indent=2, allow_nan=False) + '\n')
    file.chmod(0o600)


def devices():
    return call('/platform/devices')


def idle():
    operations = call('/platform/operations')
    if operations['reservations'] or operations['queueCount']:
        raise RuntimeError('Confirmed idle queue and device ownership are required')
    return operations


def contribution(device, enabled):
    call('/devices/' + device['deviceId'] + '/contribution',
         {'enabled': enabled, 'bootId': device['bootId']})
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        current = next(d for d in devices() if d['deviceId'] == device['deviceId'])
        if current['contributionEnabled'] == enabled:
            return current
        time.sleep(1)
    raise RuntimeError('Contribution acknowledgement timed out')


def ledger(root):
    with sqlite3.connect((root / 'ledger.sqlite').as_uri() + '?mode=ro', uri=True) as db:
        counts = dict(db.execute('SELECT a.worker_id,count(*) FROM result r JOIN attempt a USING(candidate_id,attempt_number) GROUP BY a.worker_id'))
        rewards = [list(r) for r in db.execute('SELECT c.generation,c.candidate_index,c.seed,r.reward FROM candidate c JOIN result r USING(candidate_id) ORDER BY c.generation,c.candidate_index')]
        updates = [list(r) for r in db.execute('SELECT generation,record_hash,child_weights_sha256 FROM generation_update WHERE applied_at IS NOT NULL ORDER BY generation')]
        integrity = db.execute('PRAGMA integrity_check').fetchone()[0]
    return {'acceptedResultsByWorker': counts, 'candidateRewards': rewards,
            'generationUpdates': updates, 'ledgerIntegrity': integrity}


def budget():
    # Owner reported <2 minutes for qualification; charge the full upper bound.
    seconds = 120 + 0.007097731166415744 * 3600
    for name in ['distributed.json', 'baseline.json', 'cancel.json']:
        file = STATE / name
        if file.exists():
            seconds += json.loads(file.read_text())['conservativeGpuHours'] * 3600
    return seconds


def run(cancel_test=False):
    operations = idle()
    native = [d for d in devices() if d['connectionStatus'] == 'ONLINE'
              and d['selfTest'].get('platform') == 'windows' and d['contributionEnabled']]
    if len(native) != 1:
        raise RuntimeError('Exactly one online, owner-enabled native Windows worker is required')
    worker = native[0]
    config = json.loads((PRIVATE / 'coordinator-config.json').read_text())
    coordinator = next(d for d in devices() if d['deviceId'] == config['deviceId'])
    if coordinator['connectionStatus'] != 'ONLINE':
        raise RuntimeError('The isolated local coordinator agent must be online')
    evidence_name = 'cancel.json' if cancel_test else 'distributed.json'
    if (STATE / evidence_name).exists():
        raise RuntimeError('Existing acceptance evidence is never overwritten')
    if budget() + (160 if cancel_test else 400) > 900:
        raise RuntimeError('Insufficient remaining M3a campaign budget')
    coordinator = contribution(coordinator, True)
    if operations['dispatchHeld']:
        call('/platform/maintenance/resume', {'workerConfigurationConfirmed': True})
    body = {'name': 'Native Windows safe OFF trial' if cancel_test else 'M3 native Windows replay acceptance',
        'modelName': 'Qwen/Qwen2.5-0.5B-Instruct', 'workerIds': [worker['workerId']],
        'coordinatorDeviceId': coordinator['deviceId'], 'task': 'arith16',
        'maxGenerations': 2, 'candidatesPerGeneration': 32 if cancel_test else 4, 'alpha': .001, 'sigma': .001,
        'schedulerPolicy': 'greedy', 'syncMode': 'synchronous', 'decodeEngine': 'hf_generate',
        'backupPolicy': {'interval': 1, 'retain': 1}}
    experiment = call('/experiments', body)
    run_id = experiment['experimentId']
    write('current-run.json', {'runId': run_id, 'workerId': worker['workerId'], 'phase': evidence_name})
    started = time.time()
    call('/experiments/' + run_id + '/submit', {})
    cancelled = False
    off_at = None
    last = None
    root = STATE / 'agent/runs' / run_id
    while True:
        result = call('/experiments/' + run_id)
        projection = (result['status'], result['completedGenerations'])
        if projection != last:
            print(run_id, *projection, flush=True)
            last = projection
        if cancel_test and not cancelled and (root / 'ledger.sqlite').exists():
            with sqlite3.connect((root / 'ledger.sqlite').as_uri() + '?mode=ro', uri=True) as db:
                evaluating = db.execute('SELECT count(*) FROM attempt WHERE ended_at IS NULL').fetchone()[0]
            if evaluating:
                off_at = time.time()
                contribution(worker, False)
                cancelled = True
                print('Requested owner OFF during a live candidate lease', flush=True)
        if result['status'] in TERMINAL:
            break
        if time.time() - started > (70 if cancel_test else 170) and not cancelled:
            call('/experiments/' + run_id + '/cancel', {})
            cancelled = True
            print('Deadline reached; cooperative cancellation requested', flush=True)
        time.sleep(1)
    elapsed = time.time() - started
    operations = idle()
    record = {'runId': run_id, 'status': result['status'], 'completedGenerations': result['completedGenerations'],
        'finalWeightsSha256': result.get('modelVersion'), 'wallSeconds': elapsed,
        'conservativeGpuHours': elapsed * 2 / 3600, 'queueCountAfter': operations['queueCount'],
        'reservationCountAfter': len(operations['reservations']), 'ownerOffDuringLiveLease': off_at is not None,
        **ledger(root)}
    with sqlite3.connect((Path.home() / '.config/heteroes-m2/state/product.sqlite').as_uri() + '?mode=ro', uri=True) as db:
        processes = json.loads(db.execute('SELECT processes FROM devices WHERE id=?', (worker['deviceId'],)).fetchone()[0])
    record['windowsProcessConfirmation'] = [p for p in processes if p['assignmentId'] == json.loads((root / 'assignment.json').read_text())['assignmentId']]
    # Process observations contain no compute grants; redact redundant event detail.
    for p in record['windowsProcessConfirmation']:
        p['replayEvents'] = [e for e in p.pop('events', []) if e.get('event') in ('replay', 'replay_failed', 'sync')]
    write(evidence_name, record)
    if cancel_test and cancelled:
        contribution(worker, True)  # Restore the owner's original ON preference after confirmed drain.
    print(json.dumps({k: v for k, v in record.items() if k not in ('candidateRewards', 'windowsProcessConfirmation')}, indent=2), flush=True)
    assert result['status'] == ('CANCELLED' if cancel_test else 'COMPLETED'), result.get('failureReason')
    if cancel_test:
        assert off_at is not None, 'No live candidate was stopped; do not claim the OFF gate'
    else:
        assert record['acceptedResultsByWorker'] == {worker['workerId']: 8} and len(record['generationUpdates']) == 2


def baseline():
    idle()
    if (STATE / 'baseline.json').exists():
        raise RuntimeError('Existing baseline evidence is never overwritten')
    if budget() + 150 > 900:
        raise RuntimeError('Insufficient baseline budget')
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'hetero-es-m3-runtime/src'))
    from heteroes.product.gateway import Manager
    config = json.loads((PRIVATE / 'coordinator-config.json').read_text())
    run_id = json.loads((STATE / 'distributed.json').read_text())['runId']
    python = str(Path.home() / 'miniforge3/envs/heteroes-match/bin/python')
    source = str(Path(__file__).resolve().parents[2] / 'hetero-es-m3-runtime/src')
    manager = Manager({**config, 'python': python, 'stateDirectory': str(STATE / 'baseline/runs'),
        'workerHost': '127.0.0.1', 'workerPort': 8771, 'workerUrl': 'http://127.0.0.1:8771',
        'workers': [{'id': '5070ti', 'label': '5070 Ti', 'python': python, 'source': source,
            'modelPath': config['modelPath'], 'stateDirectory': str(STATE / 'baseline/worker'), 'chunk': 16}]}, secrets.token_urlsafe(32))
    started = time.time()
    manager.submit({'runId': run_id, 'workerIds': ['5070ti'], 'workload': 'arith16',
        'maxGenerations': 2, 'candidatesPerGeneration': 4, 'alpha': .001, 'sigma': .001,
        'schedulerPolicy': 'greedy', 'syncMode': 'synchronous', 'decodeEngine': 'hf_generate'})
    manager.thread.start()
    root = manager.directory(run_id)
    while manager.state(root)['status'] not in TERMINAL:
        if time.time() - started > 100:
            (root / 'cancel.flag').touch()
        time.sleep(.5)
    state = manager.state(root)
    manager.stop.set()
    manager.thread.join(timeout=10)
    elapsed = time.time() - started
    actual = ledger(root)
    expected = json.loads((STATE / 'distributed.json').read_text())
    record = {'runId': run_id, 'status': state['status'], 'sameExperimentId': True,
        'finalWeightsSha256': state['finalWeightsSha256'], 'wallSeconds': elapsed,
        'conservativeGpuHours': elapsed / 3600, **actual,
        'exactRewardsMatch': actual['candidateRewards'] == expected['candidateRewards'],
        'exactGenerationUpdatesMatch': actual['generationUpdates'] == expected['generationUpdates'],
        'exactFinalWeightsMatch': state['finalWeightsSha256'] == expected['finalWeightsSha256']}
    record['checkpointBytesVerified'] = False
    weight = root / 'weights' / (str(state.get('finalWeightsSha256')) + '.bin')
    if weight.is_file():
        with weight.open('rb') as stream:
            record['checkpointBytesVerified'] = hashlib.file_digest(stream, 'sha256').hexdigest() == state['finalWeightsSha256']
    write('baseline.json', record)
    print(json.dumps(record, indent=2), flush=True)
    assert state['status'] == 'COMPLETED' and all(record[k] for k in ['exactRewardsMatch', 'exactGenerationUpdatesMatch', 'exactFinalWeightsMatch', 'checkpointBytesVerified'])


def main():
    global token
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--phase', choices=['status', 'run', 'baseline', 'cancel'], default='status')
    parser.add_argument('--gpu', action='store_true')
    args = parser.parse_args()
    if args.phase != 'status' and not (args.gpu and os.environ.get('HETEROES_GPU_ACCEPTANCE') == '1'):
        parser.error('GPU phases require --gpu and HETEROES_GPU_ACCEPTANCE=1')
    passwords = json.loads((Path.home() / '.config/heteroes-m2/credentials.json').read_text())
    token = call('/auth/login', {'username': 'admin', 'password': passwords['users']['admin']})['accessToken']
    if args.phase == 'status':
        print(json.dumps({'operations': {k: idle()[k] for k in ['dispatchHeld', 'queueCount', 'reservations']},
            'devices': [{k: d[k] for k in ['workerId', 'displayName', 'connectionStatus', 'contributionEnabled']} for d in devices()]}, indent=2))
    elif args.phase == 'baseline':
        baseline()
    else:
        run(cancel_test=args.phase == 'cancel')


if __name__ == '__main__':
    main()
