"""Versioned, transactional migration of the original single-lab database."""
import json

SCHEMA_VERSION = 1


def migrate(db):
    version = db.execute('PRAGMA user_version').fetchone()[0]
    if version > SCHEMA_VERSION:
        raise RuntimeError('Database belongs to a newer product version')
    if version == SCHEMA_VERSION:
        return
    # Do not rewrite experiment bodies, snapshots, sessions or FIFO sequence IDs.
    db.execute('BEGIN IMMEDIATE')
    db.execute('CREATE TABLE workspaces(id TEXT PRIMARY KEY,name TEXT NOT NULL,description TEXT NOT NULL,creator TEXT NOT NULL)')
    db.execute('CREATE TABLE memberships(workspace_id TEXT NOT NULL,user_id TEXT NOT NULL,role TEXT NOT NULL CHECK(role IN ("ADMIN","PARTICIPANT")),PRIMARY KEY(workspace_id,user_id))')
    db.execute('CREATE TABLE invitations(id TEXT PRIMARY KEY,workspace_id TEXT NOT NULL,user_id TEXT NOT NULL,status TEXT NOT NULL,created TEXT NOT NULL)')
    db.execute('CREATE UNIQUE INDEX pending_invitation ON invitations(workspace_id,user_id) WHERE status="PENDING"')
    db.execute('CREATE TABLE worker_assignments(worker_id TEXT PRIMARY KEY,owner TEXT NOT NULL,workspace_id TEXT)')
    db.execute('CREATE TABLE settings(key TEXT PRIMARY KEY,value TEXT NOT NULL)')
    db.execute('ALTER TABLE audit ADD COLUMN workspace_id TEXT')
    db.execute('UPDATE audit SET workspace_id="lab"')
    profiles = [json.loads(row['profile']) for row in db.execute('SELECT profile FROM users ORDER BY rowid')]
    # Legacy bootstrap migration only: subsequent authorization uses persisted
    # privileges and membership, never a special username.
    creator = next((p['userId'] for p in profiles if p['username']=='admin'), profiles[0]['userId'] if profiles else 'bootstrap')
    db.execute('INSERT INTO workspaces VALUES (?,?,?,?)', ('lab','HeteroES Lab','Private GPU pool · FIFO · one active experiment',creator))
    for p in profiles:
        p.update(accountStatus='ACTIVE', platformAdmin=p['userId']==creator,
                 canCreateWorkspace=p['userId']==creator)
        db.execute('UPDATE users SET profile=? WHERE id=?',(json.dumps(p),p['userId']))
        db.execute('INSERT INTO memberships VALUES (?,?,?)',('lab',p['userId'],'ADMIN' if p['userId']==creator else 'PARTICIPANT'))
    db.execute("CREATE UNIQUE INDEX username ON users(json_extract(profile,'$.username'))")
    db.execute('INSERT INTO settings VALUES (?,?)',('dispatchHold','false'))
    db.execute('PRAGMA user_version=1')
