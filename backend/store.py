"""SQLite product state. Runtime ledgers are reachable only through the control API."""
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import threading
import time
import uuid

from argon2 import PasswordHasher
from .runtime import RuntimeRejected
from .migrations import migrate

ACTIVE = {"STARTING", "RUNNING", "CANCELLING", "RECOVERING", "DRAINING", "PAUSING"}
TERMINAL = {"COMPLETED", "CANCELLED", "FAILED"}


def now():
    return datetime.now(timezone.utc).isoformat()


class Store:
    def __init__(self, path, passwords, runtime):
        self.path, self.runtime = str(path), runtime
        Path(path).parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.lock = threading.RLock()
        self.operation_lock = threading.RLock()
        self.hasher = PasswordHasher()
        self.last_error = None
        with self.db() as db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS users (id TEXT PRIMARY KEY, hash TEXT NOT NULL, profile TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS sessions (digest TEXT PRIMARY KEY, user_id TEXT NOT NULL, expires REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS experiments (id TEXT PRIMARY KEY, owner TEXT NOT NULL, body TEXT NOT NULL, snapshot TEXT);
                CREATE TABLE IF NOT EXISTS queue (sequence INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL UNIQUE);
                CREATE TABLE IF NOT EXISTS audit (sequence INTEGER PRIMARY KEY AUTOINCREMENT, actor TEXT, action TEXT, target TEXT, created TEXT);
            """)
            for name, password in passwords.items():
                profile = {"userId": name, "username": name, "displayName": name.title(), "canCreateWorkspace": False}
                # Bootstrap secrets seed an empty installation only. A renamed
                # or removed account must not be recreated on every restart.
                if db.execute('PRAGMA user_version').fetchone()[0] == 0:
                    db.execute("INSERT OR IGNORE INTO users VALUES (?,?,?)", (name, self.hasher.hash(password), json.dumps(profile)))
            db.commit()
            migrate(db)
        os.chmod(path, 0o600)
        with self.db() as db:
            mode=db.execute('SELECT value FROM settings WHERE key=?',('controlMode',)).fetchone()
            if mode and mode[0]=='agent-v2' and not getattr(runtime,'agent_mode',False):
                raise RuntimeError('This database requires agent mode; legacy dispatch would be unsafe')
        if hasattr(runtime, 'attach_store'):
            runtime.attach_store(self)
        try:
            self.ensure_workers(runtime.capabilities()['workerIds'])
        except Exception:
            self.last_error = 'WorkerConfigurationUnavailable'

    @contextmanager
    def db(self):
        with self.lock:
            connection = sqlite3.connect(self.path, timeout=20)
            connection.row_factory = sqlite3.Row
            try:
                yield connection
                connection.commit()
            except BaseException:
                connection.rollback()
                raise
            finally:
                connection.close()

    def audit(self, db, actor, action, target, workspace_id=None):
        db.execute("INSERT INTO audit(actor,action,target,created,workspace_id) VALUES (?,?,?,?,?)", (actor, action, target, now(), workspace_id))

    def ensure_workers(self, ids):
        with self.db() as db:
            initialized=bool(db.execute('SELECT value FROM settings WHERE key="workersInitialized"').fetchone())
            creator = db.execute('SELECT creator FROM workspaces WHERE id="lab"').fetchone()[0]
            disabled=self.disabled_workers(db)
            for wid in ids:
                if not db.execute('SELECT 1 FROM worker_assignments WHERE worker_id=?',(wid,)).fetchone():
                    db.execute('INSERT INTO worker_assignments VALUES (?,?,?)',(wid,creator,None if initialized else 'lab'))
                    if initialized:disabled.add(wid)
            db.execute('INSERT OR REPLACE INTO settings VALUES (?,?)',('disabledWorkers',json.dumps(sorted(disabled))))
            db.execute('INSERT OR IGNORE INTO settings VALUES (?,?)',('workersInitialized','true'))
        if self.last_error=='WorkerConfigurationUnavailable':
            self.last_error=None

    def profile(self, user_id):
        with self.db() as db:
            row = db.execute('SELECT profile FROM users WHERE id=?',(user_id,)).fetchone()
            return json.loads(row[0]) if row else None

    def workspaces(self, user_id):
        with self.db() as db:
            return [{'workspaceId':r['id'],'name':r['name'],'description':r['description'],
                     'creatorUserId':r['creator'],'role':r['role']} for r in db.execute(
                'SELECT w.*,m.role FROM workspaces w JOIN memberships m ON m.workspace_id=w.id WHERE m.user_id=? ORDER BY w.rowid',(user_id,))]

    def assignments(self, workspace_id,include_disabled=False):
        with self.db() as db:
            disabled=self.disabled_workers(db)
            return [r[0] for r in db.execute('SELECT worker_id FROM worker_assignments WHERE workspace_id=?',(workspace_id,)) if include_disabled or r[0] not in disabled]

    def disabled_workers(self,db):
        row=db.execute('SELECT value FROM settings WHERE key="disabledWorkers"').fetchone()
        return set(json.loads(row[0])) if row else set()

    def cancel_selected(self,db,worker_id):
        for row in db.execute('SELECT body FROM experiments').fetchall():
            b=json.loads(row[0])
            coordinator = b.get('coordinatorDeviceId')
            coordinator_alias = None
            if coordinator and getattr(self.runtime, 'agent_mode', False):
                row = db.execute('SELECT worker_id FROM devices WHERE id=?', (coordinator,)).fetchone()
                coordinator_alias = row[0] if row else None
            if worker_id not in set(b['workerIds']) | {coordinator_alias} or b['status'] in TERMINAL | {'DRAFT','PAUSED'}:
                continue
            b['cancelRequested']=True
            if b['status'] in ('QUEUED','PAUSED'):
                b.update(status='CANCELLED',completedAt=now(),failureReason='GPU contribution was disabled')
                db.execute('DELETE FROM queue WHERE run_id=?',(b['experimentId'],))
            else:
                b['status']='CANCELLING'
            self.save(db,b)
            self.audit(db,'system','GPU_CONTRIBUTION_DISABLED',b['experimentId'],b['workspaceId'])

    def cancel_owned(self, db, owner, workspace_id=None):
        for row in db.execute('SELECT body FROM experiments WHERE owner=?',(owner,)).fetchall():
            body = json.loads(row[0])
            if workspace_id and body['workspaceId'] != workspace_id:
                continue
            if body['status'] in TERMINAL | {'DRAFT'}:
                continue
            body['cancelRequested'] = True
            if body['status'] in ('QUEUED','PAUSED'):
                body.update(status='CANCELLED',completedAt=now(),failureReason='Resource access revoked')
                db.execute('DELETE FROM queue WHERE run_id=?',(body['experimentId'],))
            else:
                body['status']='CANCELLING'
            self.save(db,body)
            self.audit(db,'system','ACCESS_REVOKED',body['experimentId'],body['workspaceId'])

    def eligibility(self, db, body):
        row = db.execute('SELECT profile FROM users WHERE id=?',(body['ownerUserId'],)).fetchone()
        if not row or json.loads(row[0])['accountStatus']!='ACTIVE':
            return 'Owner account is not active'
        if not db.execute('SELECT 1 FROM memberships WHERE workspace_id=? AND user_id=?',
                          (body['workspaceId'],body['ownerUserId'])).fetchone():
            return 'Workspace membership was revoked'
        ids = {r[0] for r in db.execute('SELECT worker_id FROM worker_assignments WHERE workspace_id=?',(body['workspaceId'],))}
        if not set(body['workerIds']) <= ids-self.disabled_workers(db):
            return 'Selected GPU assignment changed before launch'
        if getattr(self.runtime, 'agent_mode', False):
            co = db.execute('SELECT worker_id,status,owner FROM devices WHERE id=?', (body.get('coordinatorDeviceId'),)).fetchone()
            if not co or co['status']!='APPROVED' or co['worker_id'] not in ids-self.disabled_workers(db):
                return 'Coordinator approval or workspace assignment changed'
            chosen = db.execute('SELECT owner,status FROM devices WHERE worker_id IN ('+','.join('?' for _ in body['workerIds'])+')',body['workerIds']).fetchall()
            if len(chosen)!=len(body['workerIds']) or any(d['status']!='APPROVED' or self.profile(d['owner'])['accountStatus']!='ACTIVE' for d in [co,*chosen]):
                return 'Device owner or approval was revoked'
        return None

    def get(self, run_id):
        with self.db() as db:
            row = db.execute("SELECT body FROM experiments WHERE id=?", (run_id,)).fetchone()
            return json.loads(row[0]) if row else None

    def list(self):
        with self.db() as db:
            return [json.loads(row[0]) for row in db.execute("SELECT body FROM experiments ORDER BY rowid")]

    def save(self, db, body):
        db.execute("UPDATE experiments SET body=? WHERE id=?", (json.dumps(body, allow_nan=False), body["experimentId"]))

    def create(self, owner, config, workspace_id='lab'):
        run_id = uuid.uuid4().hex
        digest = hashlib.sha256(json.dumps(config, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        body = {**config, "experimentId": run_id, "workspaceId": workspace_id, "ownerUserId": owner, "status": "DRAFT",
                "cancelRequested": False, "modelVersion": "7ae557604adf67be50417f59c2c2f167def9a775",
                "configHash": digest, "createdAt": now(), "completedGenerations": 0}
        with self.db() as db:
            db.execute("INSERT INTO experiments VALUES (?,?,?,NULL)", (run_id, owner, json.dumps(body)))
            self.audit(db, owner, "CREATE", run_id, workspace_id)
        return body

    def snapshot(self, run_id):
        with self.db() as db:
            row = db.execute("SELECT snapshot FROM experiments WHERE id=?", (run_id,)).fetchone()
            return json.loads(row[0]) if row and row[0] else {"generations": [], "candidates": [], "attempts": [], "events": [], "artifacts": []}

    def dispatch_once(self):
        with self.operation_lock:
            self._dispatch_once()

    def _dispatch_once(self):
        if getattr(self.runtime, 'agent_mode', False):
            return self._dispatch_parallel()
        return self._dispatch_legacy_once()

    def _dispatch_parallel(self):
        """Always reconcile admitted work; hold only admission of new queued work."""
        errors = []
        for active in [body for body in self.list() if body['status'] in ACTIVE]:
            try:
                self._dispatch_run(active)
            except Exception as error:
                errors.append(type(error).__name__)
        with self.db() as db:
            queued = [row[0] for row in db.execute('SELECT run_id FROM queue ORDER BY sequence')]
        for run_id in queued:
            with self.db() as db:
                # Recheck under the same lock as the queued-to-STARTING claim.
                # An operator can hold admission while reconciliation is running.
                if json.loads(db.execute('SELECT value FROM settings WHERE key="dispatchHold"').fetchone()[0]):
                    break
                active = self.get(run_id)
                if not active or active['status'] != 'QUEUED':
                    continue
                if reason := self.eligibility(db, active):
                    active.update(status='CANCELLED', cancelRequested=True, completedAt=now(), failureReason=reason)
                    self.save(db, active)
                    db.execute('DELETE FROM queue WHERE run_id=?', (run_id,))
                    self.audit(db, 'system', 'QUEUE_ACCESS_REVOKED', run_id, active['workspaceId'])
                    continue
                if waiting := self.runtime.waiting_reason(active):
                    active['waitingReason'] = waiting
                    self.save(db, active)
                    continue
                active.pop('waitingReason', None)
                active.update(status='STARTING', startedAt=now())
                self.save(db, active)
            # Reserve before considering the next job; retry this frozen run on
            # lost responses, and keep unrelated jobs progressing through errors.
            try:
                self._dispatch_run(active)
            except Exception as error:
                errors.append(type(error).__name__)
        self.last_error = errors[0] if errors else None

    def _dispatch_legacy_once(self):
        # Only one dispatcher in the supported one-process deployment. Durable state
        # is claimed before the RPC; retry uses the same run ID and frozen config.
        with self.db() as db:
            if json.loads(db.execute('SELECT value FROM settings WHERE key="dispatchHold"').fetchone()[0]):
                return
            active = next((body for body in self.list() if body["status"] in ACTIVE), None)
            if active is None:
                row = db.execute("SELECT run_id FROM queue JOIN experiments ON experiments.id=queue.run_id ORDER BY sequence LIMIT 1").fetchone()
                if row:
                    active = self.get(row[0])
                    if active["status"] != "QUEUED":
                        db.execute("DELETE FROM queue WHERE run_id=?", (row[0],))
                        return
                    reason = self.eligibility(db,active)
                    if reason:
                        active.update(status='CANCELLED',cancelRequested=True,completedAt=now(),failureReason=reason)
                        self.save(db,active)
                        db.execute('DELETE FROM queue WHERE run_id=?',(row[0],))
                        self.audit(db,'system','QUEUE_ACCESS_REVOKED',row[0],active['workspaceId'])
                        return
                    if hasattr(self.runtime, 'waiting_reason') and (waiting := self.runtime.waiting_reason(active)):
                        active['waitingReason'] = waiting
                        self.save(db, active)
                        return
                    active.pop('waitingReason', None)
                    active.update(status="STARTING", startedAt=now())
                    self.save(db, active)
        if active is None:
            return
        self._dispatch_run(active)
        self.last_error = None

    def _dispatch_run(self, active):
        run_id = active["experimentId"]
        # Submission can succeed while its response is lost. The runtime rejects
        # changes to an existing run and accepts retries of this exact payload.
        config = {"runId": run_id, "workerIds": active["workerIds"], "workload": active["task"],
                  **{key: active[key] for key in ("candidatesPerGeneration", "maxGenerations", "alpha", "sigma", "decodeEngine", "schedulerPolicy", "syncMode")}}
        if getattr(self.runtime, 'agent_mode', False):
            config.update(coordinatorDeviceId=active['coordinatorDeviceId'], backupPolicy=active.get('backupPolicy', {'interval':1,'retain':3}))
            if active.get('recipeVersion')==2:
                config.update({key:active[key] for key in ('recipeVersion','modelManifest','modelSource','datasetObjectSha256','datasetIdentity',
                    'batchSize','batchSeed','sigmaSchedule','sigmaMinimum','maxNewTokens','validationInterval')})
        try:
            self.runtime.submit(config)
        except RuntimeRejected as error:
            with self.db() as db:
                body = self.get(run_id)
                body.update(status="FAILED", failureReason=str(error), completedAt=now())
                self.save(db, body)
                db.execute("DELETE FROM queue WHERE run_id=?", (run_id,))
            return
        current = self.get(run_id)
        if current.get("cancelRequested"):
            self.runtime.cancel(run_id)
        elif current.get('pauseRequested'):
            self.runtime.pause(run_id)
        snapshot = self.runtime.snapshot(run_id)
        with self.db() as db:
            body = self.get(run_id)
            state = snapshot["state"]
            body["status"] = state["status"]
            if body.get('cancelRequested') and body['status']=='PAUSED':
                body['status']='CANCELLED'
            if body.get('pauseRequested') and not body.get('cancelRequested') and body['status'] in ('STARTING','RUNNING'):
                body['status']='PAUSING'
            if state.get('pauseCheckpoint'):
                body['pauseCheckpoint']=state['pauseCheckpoint']
            if body['status']=='PAUSED':
                body['pausedAt']=now()
                db.execute('DELETE FROM queue WHERE run_id=?',(run_id,))
            if "cloudSync" in snapshot:
                previous=body.get('cloudSync',{})
                incoming=snapshot['cloudSync']
                body['cloudSync']={**incoming}
                if previous.get('lastCloudGeneration',-1)>incoming.get('lastCloudGeneration',-1):
                    body['cloudSync'].update({k:previous[k] for k in ('lastCloudGeneration','pointId') if k in previous})
            generations = snapshot["generations"]
            complete = [item for item in generations if item["status"] == "COMPLETED"]
            body["completedGenerations"] = snapshot.get('completedGenerationCount',len(complete))
            body['monitoringPartial']=bool(snapshot.get('monitoringPartial'))
            if snapshot.get('studyMetrics'):
                body['studyMetrics']=snapshot['studyMetrics']
                best=snapshot['studyMetrics'].get('best') or {}
                if 'validationAccuracy' in best:body['validationScore']=best['validationAccuracy']
                if 'testAccuracy' in snapshot['studyMetrics']:body['testScore']=snapshot['studyMetrics']['testAccuracy']
            latest=snapshot.get('latestGeneration') or (generations[-1] if generations else None)
            if latest:
                body["currentGenerationId"] = latest["generationId"]
                body["committedCandidateCount"] = latest["committedCandidateCount"]
                body["modelVersion"] = latest["modelVersion"]
            if state.get("failureReason"):
                body["failureReason"] = state["failureReason"]
            if state.get("finalWeightsSha256"):
                body["modelVersion"] = state["finalWeightsSha256"]
            elif body["status"] in TERMINAL and snapshot.get("checkpointSha256"):
                body["modelVersion"] = snapshot["checkpointSha256"]
            if body["status"] in TERMINAL:
                body["completedAt"] = now()
                db.execute("DELETE FROM queue WHERE run_id=?", (run_id,))
            self.save(db, body)
            db.execute("UPDATE experiments SET snapshot=? WHERE id=?", (json.dumps(snapshot, allow_nan=False), run_id))

    def dispatch(self, stop):
        while not stop.wait(1):
            try:
                self.dispatch_once()
            except Exception as error:
                self.last_error = type(error).__name__  # errors never become fabricated success/rewards
