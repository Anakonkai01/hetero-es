"""Helpers shared by the backend tests.

The labs they build run in agent mode, like the live lab: a device pairs with a one-time code, an administrator
approves it into a workspace, and its agent polls for commands. The fixtures that use these helpers are in conftest.py.
"""
import uuid

USERS = {'admin': 'test-admin-pass', 'participant': 'test-user-pass'}
AGENT_COMMANDS = 'SET_CONTRIBUTION,COORDINATE,START_WORKER,STOP_WORKER,CANCEL_ASSIGNMENT,PAUSE_ASSIGNMENT,UPDATE_BACKUP_POLICY'


def login(client, name):
    result = client.post('/api/v1/auth/login', json={'username': name, 'password': USERS.get(name, 'test-user-pass')})
    assert result.status_code == 200
    return {'Authorization': 'Bearer ' + result.json()['accessToken'], 'X-Workspace-Id': 'lab'}


def draft(client, headers, **changes):
    """Create a Recipe v1 draft. Without an explicit coordinator it takes the workspace's first approved coordinator."""
    body = dict(name='Test run', modelName='Qwen/Qwen2.5-0.5B-Instruct', modelArtifactId='qwen-pinned',
                schedulerPolicy='greedy', syncMode='synchronous', workerIds=['5070ti'], task='arith16',
                maxGenerations=3, candidatesPerGeneration=8, alpha=.001, sigma=.001, decodeEngine='hf_generate')
    if 'coordinatorDeviceId' not in changes:
        coordinators = client.get('/api/v1/capabilities', headers=headers).json().get('coordinatorDevices') or []
        if coordinators:
            body['coordinatorDeviceId'] = coordinators[0]['deviceId']
    return client.post('/api/v1/experiments', json={**body, **changes}, headers=headers)


def enroll(lab, alias='test-gpu', coordinator=True, name=None):
    """Pair one device with a fresh code; it stays PENDING. Returns (enrollment, agent headers)."""
    client, store, runtime, admin = lab
    code = client.post('/api/v1/devices/pairing-codes', headers=admin).json()['code']
    data = {'code': code, 'workerId': alias, 'displayName': name or alias,
            'selfTest': {'passed': True, 'coordinator': coordinator, 'gpuName': 'Fake CPU test GPU',
                         'vramTotalMb': 12000, 'noiseVersion': 'numpy_pcg64_normal_f32_to_f16_v1',
                         'gpuUUID': 'GPU-' + str(uuid.uuid5(uuid.NAMESPACE_DNS, alias))},
            'computeUrl': 'http://100.64.0.1:8769'}
    response = client.post('/api/v1/device/enroll', json=data)
    assert response.status_code == 201, response.text
    d = response.json()
    auth = {'Authorization': 'Bearer ' + d['deviceToken'], 'X-HeteroES-Agent-Commands': AGENT_COMMANDS}
    assert client.post('/api/v1/device/enroll', json=data).status_code == 409
    return d, auth


def pair(lab, alias='test-gpu', coordinator=True):
    """Pair, approve into the workspace 'lab' and boot one device; returns (enrollment, agent headers)."""
    client, store, runtime, admin = lab
    d, auth = enroll(lab, alias, coordinator)
    assert client.patch('/api/v1/platform/devices/' + d['deviceId'], json={'approved': True, 'workspaceId': 'lab'},
                        headers=admin).status_code == 200
    boot(client, auth, 'boot-1')
    return d, auth


def boot(client, auth, boot_id, **changes):
    data = {'bootId': boot_id, 'contribution': False, 'processes': [], 'reports': [], **changes}
    response = client.post('/api/v1/device/poll', headers=auth, json=data)
    assert response.status_code == 200, response.text
    return response.json()


def enable(lab, d, auth, boot_id='boot-1'):
    client, _, _, admin = lab
    r = client.post('/api/v1/devices/' + d['deviceId'] + '/contribution', headers=admin,
                    json={'enabled': True, 'bootId': boot_id})
    assert r.status_code == 200, r.text
    return boot(client, auth, boot_id, contribution=True)


def queued(lab, d, **changes):
    """Draft and submit a run that uses device `d` as coordinator and only worker; returns the run id."""
    client, store, _, admin = lab
    r = draft(client, admin, **{'workerIds': [d['workerId']], 'coordinatorDeviceId': d['deviceId'], **changes})
    assert r.status_code == 200, r.text
    rid = r.json()['experimentId']
    assert client.post(f'/api/v1/experiments/{rid}/submit', headers=admin).status_code == 200
    return rid


def submitted(runtime):
    """Run ids the lab has handed to devices: one assignment per run and epoch."""
    return [r['runId'] for r in runtime.runs()]


def pending_commands(runtime, kind):
    """Every unacknowledged device command of this kind, as (device id, command)."""
    return [(d['deviceId'], c) for d in runtime.devices() for c in runtime.commands(d['deviceId']) if c['kind'] == kind]
