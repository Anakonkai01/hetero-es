"""Independent product contracts: identity, workspace isolation and revocation."""
import json
import sqlite3

from backend.store import Store
from test_api import setup, login, draft


def register(client, name="alice"):
    response = client.post('/api/v1/auth/register', json={
        'username': name, 'password': 'long-test-password', 'displayName': name.title()})
    assert response.status_code == 201, response.text
    session = client.post('/api/v1/auth/login', json={'username': name, 'password': 'long-test-password'})
    assert session.status_code == 200
    return response.json(), {'Authorization': 'Bearer ' + session.json()['accessToken']}


def activate(client, admin, profile, **changes):
    response = client.patch('/api/v1/platform/users/' + profile['userId'],
        json={'accountStatus': 'ACTIVE', **changes}, headers=admin)
    assert response.status_code == 200, response.text
    return response.json()


def test_pending_registration_requires_approval_and_creation_permission(setup):
    client, _, _ = setup
    admin = login(client, 'admin')
    profile, alice = register(client)
    assert profile['accountStatus'] == 'PENDING'
    assert client.get('/api/v1/auth/session', headers=alice).json()['workspaces'] == []
    assert client.get('/api/v1/models', headers={**alice, 'X-Workspace-Id': 'lab'}).status_code == 403
    assert client.post('/api/v1/workspaces', json={'name': 'Alice lab'}, headers=alice).status_code == 403
    activate(client, admin, profile)
    assert client.post('/api/v1/workspaces', json={'name': 'Alice lab'}, headers=alice).status_code == 403
    activate(client, admin, profile, canCreateWorkspace=True)
    result = client.post('/api/v1/workspaces', json={'name': 'Alice lab'}, headers=alice)
    assert result.status_code == 201
    assert result.json()['role'] == 'ADMIN'
    assert client.patch('/api/v1/profile', json={'platformAdmin': True}, headers=alice).status_code == 422


def test_workspace_and_every_child_route_are_isolated_even_for_platform_admin(setup):
    client, store, _ = setup
    admin = login(client, 'admin')
    profile, alice = register(client)
    activate(client, admin, profile, canCreateWorkspace=True)
    ws = client.post('/api/v1/workspaces', json={'name': 'Alice lab'}, headers=alice).json()['workspaceId']
    with store.db() as db:
        db.execute('UPDATE worker_assignments SET workspace_id=? WHERE worker_id=?', (ws, '3060'))
    scoped_alice = {**alice, 'X-Workspace-Id': ws}
    run_id = draft(client, scoped_alice, workerIds=['3060']).json()['experimentId']
    assert client.get('/api/v1/experiments', headers=admin).json() == []
    assert client.get('/api/v1/experiments', headers={**admin, 'X-Workspace-Id': ws}).status_code == 403
    for route in (f'/experiments/{run_id}', f'/experiments/{run_id}/generations',
                  f'/generations/{run_id}.g0/candidates', f'/candidates/{run_id}.g0.c0',
                  f'/attempts/{run_id}.g0.c0.a1', f'/artifacts/{run_id}.config.json/download'):
        assert client.get('/api/v1'+route, headers=admin).status_code == 404
    for route in ('events', 'artifacts'):
        assert client.get('/api/v1/'+route, headers=admin).json() == []
    assert draft(client, scoped_alice, workerIds=['5070ti']).status_code == 422


def test_invitation_acceptance_last_admin_and_membership_revocation(setup):
    client, store, runtime = setup
    admin = login(client, 'admin')
    profile, alice = register(client)
    activate(client, admin, profile)
    invite = client.post('/api/v1/workspaces/lab/invitations', json={'username': 'alice'}, headers=admin)
    assert invite.status_code == 201
    iid = invite.json()['invitationId']
    participant = login(client, 'participant')
    assert client.post(f'/api/v1/my-invitations/{iid}/accept', headers=participant).status_code == 404
    assert client.post(f'/api/v1/my-invitations/{iid}/accept', headers=alice).status_code == 200
    scoped_alice = {**alice, 'X-Workspace-Id': 'lab'}
    assert client.delete('/api/v1/workspaces/lab/members/admin', headers=admin).status_code == 409
    assert client.patch('/api/v1/workspaces/lab/members/admin', json={'role': 'PARTICIPANT'}, headers=admin).status_code == 409
    ids = [draft(client, scoped_alice, name=f'Alice {i}').json()['experimentId'] for i in range(2)]
    for rid in ids:
        client.post(f'/api/v1/experiments/{rid}/submit', headers=scoped_alice)
    store.dispatch_once()
    assert client.delete('/api/v1/workspaces/lab/members/'+profile['userId'], headers=admin).status_code == 204
    assert client.get('/api/v1/experiments', headers=scoped_alice).status_code == 403
    assert store.get(ids[0])['cancelRequested'] is True
    assert store.get(ids[1])['status'] == 'CANCELLED'
    store.dispatch_once()
    assert runtime.runs[ids[0]]['state']['status'] == 'CANCELLED'
    assert len(runtime.submissions) == 1


def test_suspension_revokes_sessions_cancels_queue_and_preserves_evidence(setup):
    client, store, _ = setup
    admin, participant = login(client, 'admin'), login(client, 'participant')
    run = draft(client, participant).json()['experimentId']
    client.post(f'/api/v1/experiments/{run}/submit', headers=participant)
    result = client.patch('/api/v1/platform/users/participant', json={'accountStatus':'SUSPENDED'}, headers=admin)
    assert result.status_code == 200
    assert client.get('/api/v1/auth/session', headers=participant).status_code == 401
    assert store.get(run)['status'] == 'CANCELLED'
    assert store.get(run)['ownerUserId'] == 'participant'
    assert client.get('/api/v1/platform/users', headers=login(client, 'participant')).status_code == 403


def test_password_change_revokes_other_sessions_and_does_not_allow_privilege_edits(setup):
    client, _, _ = setup
    first, other = login(client, 'participant'), login(client, 'participant')
    assert client.post('/api/v1/auth/password', json={
        'currentPassword':'test-user-pass', 'newPassword':'updated-long-password'}, headers=first).status_code == 204
    assert client.get('/api/v1/auth/session', headers=first).status_code == 200
    assert client.get('/api/v1/auth/session', headers=other).status_code == 401
    assert client.post('/api/v1/auth/login', json={'username':'participant','password':'test-user-pass'}).status_code == 401
    assert client.patch('/api/v1/profile', json={'canCreateWorkspace':True}, headers=first).status_code == 422


def test_migration_preserves_legacy_bytes_queue_and_ids(tmp_path, setup):
    _, _, runtime = setup
    path = tmp_path/'legacy.sqlite'
    body = {'experimentId':'fixed-id', 'workspaceId':'lab', 'ownerUserId':'participant', 'status':'QUEUED',
            'modelVersion':'checkpoint-hash', 'workerIds':['5070ti']}
    with sqlite3.connect(path) as db:
        db.executescript('''CREATE TABLE users(id TEXT PRIMARY KEY, hash TEXT NOT NULL, profile TEXT NOT NULL);
        CREATE TABLE sessions(digest TEXT PRIMARY KEY,user_id TEXT NOT NULL,expires REAL NOT NULL);
        CREATE TABLE experiments(id TEXT PRIMARY KEY,owner TEXT NOT NULL,body TEXT NOT NULL,snapshot TEXT);
        CREATE TABLE queue(sequence INTEGER PRIMARY KEY AUTOINCREMENT,run_id TEXT UNIQUE NOT NULL);
        CREATE TABLE audit(sequence INTEGER PRIMARY KEY AUTOINCREMENT,actor TEXT,action TEXT,target TEXT,created TEXT);''')
        for name in ('admin','participant'):
            db.execute('INSERT INTO users VALUES (?,?,?)', (name,'preserved-hash',json.dumps({'userId':name,'username':name})))
        db.execute('INSERT INTO experiments VALUES (?,?,?,?)',('fixed-id','participant',json.dumps(body),'preserved-snapshot'))
        db.execute('INSERT INTO queue VALUES (?,?)',(42,'fixed-id'))
    Store(path, {}, runtime)
    Store(path, {}, runtime)
    with sqlite3.connect(path) as db:
        assert db.execute('PRAGMA user_version').fetchone()[0] == 1
        assert db.execute('SELECT body,snapshot FROM experiments').fetchone() == (json.dumps(body),'preserved-snapshot')
        assert db.execute('SELECT sequence,run_id FROM queue').fetchone() == (42,'fixed-id')
        assert db.execute('SELECT hash FROM users WHERE id="admin"').fetchone()[0] == 'preserved-hash'
        assert db.execute('SELECT count(*) FROM memberships').fetchone()[0] == 2


def test_dispatch_revalidates_assignment_before_launch(setup):
    client, store, runtime = setup
    admin = login(client, 'admin')
    rid = draft(client, admin).json()['experimentId']
    client.post(f'/api/v1/experiments/{rid}/submit', headers=admin)
    with store.db() as db:
        db.execute('UPDATE worker_assignments SET workspace_id=NULL WHERE worker_id="5070ti"')
    store.dispatch_once()
    assert runtime.submissions == []
    assert store.get(rid)['status'] == 'CANCELLED'


def test_platform_privilege_is_persisted_independently_of_username(setup):
    client,store,_=setup
    admin=login(client,'admin')
    assert client.patch('/api/v1/platform/users/admin',json={'platformAdmin':False},headers=admin).status_code==409
    # Renaming the bootstrap account in persisted state preserves its real
    # privileges; an unrelated user named admin receives no privilege by name.
    with store.db() as db:
        p=store.profile('admin');p['username']='operator'
        db.execute('UPDATE users SET profile=? WHERE id="admin"',(json.dumps(p),))
    response=client.post('/api/v1/auth/login',json={'username':'operator','password':'test-admin-pass'})
    assert response.status_code==200
    headers={'Authorization':'Bearer '+response.json()['accessToken']}
    assert client.get('/api/v1/platform/users',headers=headers).status_code==200
    p,new_admin=register(client,'admin');activate(client,headers,p)
    assert client.get('/api/v1/platform/users',headers=new_admin).status_code==403
    assert client.get('/api/v1/experiments',headers={**new_admin,'X-Workspace-Id':'lab'}).status_code==403


def test_personal_gpu_inventory_is_owner_scoped_and_masks_run_identifiers(setup):
    client,_,runtime=setup
    runtime.workers=lambda:[{'workerId':'5070ti','allocatedTo':'another-private-run'},
                           {'workerId':'3060','allocatedTo':None}]
    participant=login(client,'participant');admin=login(client,'admin')
    assert client.get('/api/v1/my-workers',headers=participant).json()==[]
    result=client.get('/api/v1/my-workers',headers=admin)
    assert result.status_code==200 and len(result.json())==2
    assert 'another-private-run' not in result.text
