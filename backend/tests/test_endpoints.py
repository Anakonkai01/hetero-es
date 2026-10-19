import json
import pytest
from pydantic import ValidationError
from backend.devices import Enrollment, EndpointUpdate
from labkit import boot, enable, pair, queued


def test_public_compute_requires_tls_and_private_bulk():
    assert EndpointUpdate(computeUrl='https://compute.example.org', bulkUrl='http://100.64.0.1:8765').computeUrl == 'https://compute.example.org'
    for url in ('http://compute.example.org', 'https://user:secret@compute.example.org',
                'https://compute.example.org/v1', 'https://compute.example.org?token=secret'):
        with pytest.raises(ValidationError):
            EndpointUpdate(computeUrl=url, bulkUrl='http://100.64.0.1:8765')
    with pytest.raises(ValidationError):
        EndpointUpdate(computeUrl='https://compute.example.org')
    with pytest.raises(ValueError):
        Enrollment.private_compute('https://compute.example.org')
    with pytest.raises(ValidationError):
        EndpointUpdate(computeUrl='https://compute.example.org', bulkUrl='https://bulk.example.org')


def test_idle_address_change_preserves_identity_and_freezes_assignment(lab):
    c, s, r, a = lab
    d, auth = pair(lab)
    endpoint = {'computeUrl':'https://first.trycloudflare.com', 'bulkUrl':'http://100.64.0.1:8765'}
    response = c.patch('/api/v1/devices/'+d['deviceId']+'/endpoints', headers=a, json=endpoint)
    assert response.status_code == 200, response.text
    assert response.json()['deviceId'] == d['deviceId']
    assert boot(c, auth, 'boot-1')['desiredContribution'] is False
    enable(lab, d, auth)
    assert c.patch('/api/v1/devices/'+d['deviceId']+'/endpoints', headers=a, json=endpoint).status_code == 409
    queued(lab,d)
    s.dispatch_once()
    assignment = r.runs()[0]
    with s.db() as db:
        frozen = json.loads(db.execute('SELECT body FROM assignments WHERE id=?',(assignment['assignmentId'],)).fetchone()[0])
    assert frozen['computeUrl'] == endpoint['computeUrl']
    assert frozen['bulkUrl'] == endpoint['bulkUrl']
    body = {'assignmentId':assignment['assignmentId'], 'epoch':assignment['epoch'],
            'workerId':d['workerId'], 'action':'start'}
    assert c.post('/api/v1/device/worker-command', headers=auth, json=body).status_code == 200
    command = next(x for x in r.commands(d['deviceId']) if x['kind']=='START_WORKER')
    assert command['bulkUrl'] == endpoint['bulkUrl']
    # Turning OFF alone is not proof that the reserved processes have stopped.
    c.post('/api/v1/devices/'+d['deviceId']+'/contribution', headers=a, json={'enabled':False,'bootId':'boot-1'})
    assert c.patch('/api/v1/devices/'+d['deviceId']+'/endpoints', headers=a, json=endpoint).status_code == 409


def test_token_endpoint_change_needs_current_boot_and_off(lab):
    c, _, _, _ = lab
    d, auth = pair(lab)
    body = {'computeUrl':'https://new.trycloudflare.com', 'bulkUrl':'http://100.64.0.1:8765','bootId':'boot-1'}
    assert c.patch('/api/v1/device/endpoints', json=body).status_code == 401
    assert c.patch('/api/v1/device/endpoints', headers=auth, json={**body,'bootId':'old'}).status_code == 409
    assert c.patch('/api/v1/device/endpoints', headers=auth, json=body).status_code == 200
