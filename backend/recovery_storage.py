"""Local recovery storage. Manifest publication is the commit."""
import logging
from .migrations import initialize_recovery_schema, initialize_recovery_downloads_schema
from .policies import backup_policy
import hashlib
import json
import re
import threading
import time
import uuid
HEX = re.compile('[a-f0-9]{64}')
UUID = re.compile('[a-f0-9]{32}')

class QuotaExceeded(RuntimeError):
    pass

class RecoveryStorage:
    # Legacy cloud_* table names preserve compatibility with existing lab databases.

    def __init__(self, store, backend, quota_bytes=8000000000):
        self.store = store
        self.backend = backend
        self.quota = quota_bytes
        self.lock = threading.RLock()
        with store.db() as db:
            initialize_recovery_downloads_schema(db)
        self.pending = set()

    def validate_manifest(self, m):
        if not isinstance(m, dict) or m.get('formatVersion') != 1 or any((not isinstance(m.get(k), str) or not UUID.fullmatch(m[k]) for k in ('pointId', 'runId'))):
            raise ValueError('Invalid recovery identity')
        if type(m.get('generation')) is not int or m['generation'] < 0 or type(m.get('final')) is not bool:
            raise ValueError('Invalid generation')
        backup_policy(m.get('backupPolicy', {}))
        files = m.get('files')
        if not isinstance(files, dict) or not {'ledger.sqlite', 'config.json', 'identity.json'} <= files.keys() or (not 4 <= len(files) <= 5):
            raise ValueError('Incomplete recovery manifest')
        for name, meta in files.items():
            if name not in ('ledger.sqlite', 'config.json', 'identity.json') and (not re.fullmatch('weights/[a-f0-9]{64}\\.bin', name)):
                raise ValueError('Unsafe recovery path')
            if not isinstance(meta, dict) or not isinstance(meta.get('sha256'), str) or (not HEX.fullmatch(meta['sha256'])) or (type(meta.get('sizeBytes')) is not int) or (not 0 < meta['sizeBytes'] <= 5000000000):
                raise ValueError('Invalid recovery object')
            if name.startswith('weights/') and name[8:-4] != meta['sha256']:
                raise ValueError('Weights name disagrees with checksum')
        for key in ('childWeightsSha256', 'parentWeightsSha256'):
            if not isinstance(m.get(key), str) or not HEX.fullmatch(m[key]) or 'weights/' + m[key] + '.bin' not in files:
                raise ValueError('Missing canonical weights')
        if len(json.dumps(m)) > 32768:
            raise ValueError('Manifest is too large')

    def usage(self):
        observed = self.backend.inventory()
        with self.store.db() as db:
            reserved = 2 * db.execute('SELECT coalesce(sum(size),0) FROM cloud_objects WHERE status!="READY"').fetchone()[0]
        return {'quotaBytes': self.quota, 'observedBytes': observed, 'reservedBytes': reserved, 'storageMode': getattr(self.backend, 'mode', 'local'), 'warning': observed + reserved >= self.quota * 0.8}

    def begin(self, m):
        self.validate_manifest(m)
        with self.lock:
            with self.store.db() as db:
                old = db.execute('SELECT manifest,status FROM recovery_points WHERE id=?', (m['pointId'],)).fetchone()
                if old and json.loads(old[0]) != m:
                    raise ValueError('Frozen recovery manifest changed')
                if old and old['status'] == 'READY':
                    return {'pointId': m['pointId'], 'status': 'READY', 'objects': []}
                unique = {}
                for meta in m['files'].values():
                    if meta['sha256'] in unique and unique[meta['sha256']] != meta['sizeBytes']:
                        raise ValueError('Hash/size mismatch')
                    unique[meta['sha256']] = meta['sizeBytes']
                existing = {r['sha']: dict(r) for r in db.execute('SELECT * FROM cloud_objects')}
                if any((sha in existing and existing[sha]['size'] != size for sha, size in unique.items())):
                    raise ValueError('Stored hash/size mismatch')
            usage = self.usage()
            new_bytes = 2 * sum((size for sha, size in unique.items() if sha not in existing))
            if usage['observedBytes'] + usage['reservedBytes'] + new_bytes + len(json.dumps(m)) > self.quota:
                raise QuotaExceeded('Recovery storage quota reached; compute continues with local recovery points')
            plans = []
            with self.store.db() as db:
                db.execute('INSERT OR IGNORE INTO recovery_points VALUES (?,?,?,?,?,?,NULL,?)', (m['pointId'], m['runId'], m['generation'], m['final'], 'PENDING', json.dumps(m), time.time()))
                for sha, size in unique.items():
                    db.execute('INSERT OR IGNORE INTO cloud_objects VALUES (?,?,"PENDING",NULL,NULL)', (sha, size))
                    db.execute('INSERT OR IGNORE INTO cloud_refs VALUES (?,?)', (m['pointId'], sha))
            for sha, size in unique.items():
                entry = existing.get(sha)
                if entry and entry['status'] in ('READY', 'UPLOADED'):
                    continue
                with self.store.db() as db:
                    row = db.execute('SELECT * FROM cloud_objects WHERE sha=?', (sha,)).fetchone()
                if row['upload_plan'] and (row['expires'] or 0) > time.time() + 30:
                    plan = json.loads(row['upload_plan'])
                else:
                    if row['upload_plan']:
                        previous = json.loads(row['upload_plan'])
                        if previous.get('uploadId'):
                            self.backend.abort(previous['key'], previous['uploadId'])
                    plan = self.backend.upload_plan('uploads/' + sha + '/' + uuid.uuid4().hex, size)
                    with self.store.db() as db:
                        db.execute('UPDATE cloud_objects SET upload_plan=?,expires=? WHERE sha=?', (json.dumps(plan), time.time() + 900, sha))
                plans.append({'sha256': sha, 'sizeBytes': size, **plan})
            return {'pointId': m['pointId'], 'status': 'PENDING', 'objects': plans}

    def complete_object(self, point_id, sha, parts):
        with self.lock:
            with self.store.db() as db:
                row = db.execute('SELECT o.* FROM cloud_objects o JOIN cloud_refs r ON o.sha=r.sha WHERE r.point_id=? AND o.sha=?', (point_id, sha)).fetchone()
                if not row:
                    raise ValueError('Object is not referenced by this point')
                if row['status'] in ('READY', 'UPLOADED'):
                    return
                plan = json.loads(row['upload_plan'])
            if plan['mode'] == 'multipart':
                if len(parts) != len(plan['parts']) or [p['PartNumber'] for p in parts] != list(range(1, len(parts) + 1)):
                    raise ValueError('Incomplete multipart upload')
                self.backend.complete(plan['key'], plan['uploadId'], parts)
            with self.store.db() as db:
                db.execute('UPDATE cloud_objects SET status="UPLOADED" WHERE sha=?', (sha,))

    def verify(self, point_id):
        with self.lock:
            with self.store.db() as db:
                row = db.execute('SELECT * FROM recovery_points WHERE id=?', (point_id,)).fetchone()
                if not row:
                    raise ValueError('Point not found')
                m = json.loads(row['manifest'])
            try:
                for sha in {meta['sha256'] for meta in m['files'].values()}:
                    with self.store.db() as db:
                        obj = db.execute('SELECT * FROM cloud_objects WHERE sha=?', (sha,)).fetchone()
                    if obj['status'] == 'READY':
                        continue
                    hasher = hashlib.sha256()
                    size = 0
                    plan = json.loads(obj['upload_plan'])
                    upload_key = plan['key']
                    if hasattr(self.backend, 'read_version'):
                        etag, chunks = self.backend.read_version(upload_key)
                    else:
                        etag = None
                        chunks = self.backend.get(upload_key)
                    for chunk in chunks:
                        hasher.update(chunk)
                        size += len(chunk)
                        if size > obj['size']:
                            raise ValueError('Object checksum/size mismatch')
                    if size != obj['size'] or hasher.hexdigest() != sha:
                        raise ValueError('Object checksum/size mismatch')
                    self.backend.publish_upload(upload_key, 'objects/' + sha, etag)
                    with self.store.db() as db:
                        db.execute('UPDATE cloud_objects SET status="READY",upload_plan=NULL,expires=NULL WHERE sha=?', (sha,))
                self.backend.put('manifests/' + point_id + '.json', json.dumps(m, sort_keys=True).encode())
                with self.store.db() as db:
                    db.execute('UPDATE recovery_points SET status="READY",error=NULL WHERE id=?', (point_id,))
                self.retain(m['runId'], m['backupPolicy']['retain'])
                with self.store.db() as db:
                    body = self.store.get(m['runId'])
                    if body:
                        old = body.get('cloudSync', {})
                        if old.get('lastCloudGeneration', -1) <= m['generation']:
                            body['cloudSync'] = {'status': 'READY', 'lastCloudGeneration': m['generation'], 'pointId': point_id}
                            self.store.save(db, body)
            except Exception as error:
                if isinstance(error, ValueError):
                    with self.store.db() as db:
                        db.execute('UPDATE cloud_objects SET status="PENDING",upload_plan=NULL,expires=NULL WHERE sha=?', (sha,))
                with self.store.db() as db:
                    db.execute('UPDATE recovery_points SET status=?,error=? WHERE id=?', ('ERROR', type(error).__name__, point_id))
                raise

    def verify_background(self, point_id):
        with self.lock:
            if point_id in self.pending:
                return
            self.pending.add(point_id)

        def work():
            try:
                self.verify(point_id)
            except Exception as error:
                logging.getLogger(__name__).warning('Recovery verification failed: %s', type(error).__name__)
            finally:
                with self.lock:
                    self.pending.discard(point_id)
        threading.Thread(target=work, daemon=True).start()

    def points(self, run_id):
        with self.store.db() as db:
            return [{'pointId': r['id'], 'generation': r['generation'], 'final': bool(r['final']), 'status': r['status'], 'errorType': r['error']} for r in db.execute('SELECT * FROM recovery_points WHERE run_id=? ORDER BY generation DESC,created DESC', (run_id,))]

    def manifest(self, point_id):
        with self.store.db() as db:
            row = db.execute('SELECT manifest,status FROM recovery_points WHERE id=?', (point_id,)).fetchone()
            if not row or row['status'] != 'READY':
                raise ValueError('Verified recovery point unavailable')
            return json.loads(row['manifest'])

    def retain(self, run_id, count):
        points = [p for p in self.points(run_id) if p['status'] == 'READY' and (not p['final'])]
        for point in points[count:]:
            self.delete_point(point['pointId'])

    def delete_point(self, point_id):
        with self.lock:
            self.backend.delete('manifests/' + point_id + '.json')
            with self.store.db() as db:
                db.execute('DELETE FROM cloud_refs WHERE point_id=?', (point_id,))
                db.execute('DELETE FROM recovery_points WHERE id=?', (point_id,))
                orphaned = [dict(r) for r in db.execute('SELECT * FROM cloud_objects o WHERE NOT EXISTS(SELECT 1 FROM cloud_refs r WHERE r.sha=o.sha)')]
            for obj in orphaned:
                plan = json.loads(obj['upload_plan']) if obj['upload_plan'] else {}
                if plan.get('uploadId'):
                    self.backend.abort(plan['key'], plan['uploadId'])
                if plan.get('key'):
                    self.backend.delete(plan['key'])
                self.backend.delete('objects/' + obj['sha'])
                with self.store.db() as db:
                    db.execute('DELETE FROM cloud_objects WHERE sha=?', (obj['sha'],))

def install_storage_routes(app, store, storage, device_auth, user, scoped, authorized):
    import secrets
    from fastapi import Depends, HTTPException, Request, Response
    from fastapi.responses import RedirectResponse
    from pydantic import BaseModel, ConfigDict, Field

    class Begin(BaseModel):
        model_config = ConfigDict(extra='forbid')
        assignmentId: str
        epoch: int
        manifest: dict

    class Finish(BaseModel):
        model_config = ConfigDict(extra='forbid')
        assignmentId: str
        epoch: int
        pointId: str
        sha256: str
        parts: list[dict] = Field(default_factory=list, max_length=10000)

    def grant(device, assignment_id, epoch, run_id):
        with store.db() as db:
            row = db.execute('SELECT coordinator,epoch,run_id FROM assignments WHERE id=?', (assignment_id,)).fetchone()
            if not row or (row['coordinator'], row['epoch'], row['run_id']) != (device['id'], epoch, run_id):
                raise HTTPException(403, 'Recovery upload is outside this assignment')

    def point_run(point_id):
        with store.db() as db:
            row = db.execute('SELECT run_id FROM recovery_points WHERE id=?', (point_id,)).fetchone()
            if not row:
                raise HTTPException(404, 'Recovery point not found')
            return row[0]

    def storage_error(error):
        raise HTTPException(409 if isinstance(error, QuotaExceeded) else 422, 'Recovery quota reached; local computation continues' if isinstance(error, QuotaExceeded) else 'Recovery storage operation failed') from None

    @app.post('/api/v1/device/recovery-points')
    def begin(body: Begin, current=Depends(device_auth)):
        grant(current, body.assignmentId, body.epoch, body.manifest.get('runId'))
        try:
            return storage.begin(body.manifest)
        except (ValueError, QuotaExceeded) as error:
            storage_error(error)

    @app.post('/api/v1/device/recovery-points/complete-object')
    def complete(body: Finish, current=Depends(device_auth)):
        grant(current, body.assignmentId, body.epoch, point_run(body.pointId))
        try:
            storage.complete_object(body.pointId, body.sha256, body.parts)
        except (ValueError, QuotaExceeded) as error:
            storage_error(error)
        return {'ok': True}

    @app.post('/api/v1/device/recovery-points/{point_id}/verify')
    def verify(point_id: str, body: dict, current=Depends(device_auth)):
        grant(current, body.get('assignmentId'), body.get('epoch'), point_run(point_id))
        storage.verify_background(point_id)
        return {'status': 'VERIFYING'}

    @app.get('/api/v1/device/recovery-points/{point_id}')
    def device_status(point_id: str, current=Depends(device_auth)):
        run_id = point_run(point_id)
        with store.db() as db:
            row = db.execute('SELECT coordinator FROM assignments WHERE run_id=? ORDER BY epoch DESC LIMIT 1', (run_id,)).fetchone()
            if not row or row[0] != current['id']:
                raise HTTPException(403, 'Coordinator identity required')
        return next((p for p in storage.points(run_id) if p['pointId'] == point_id))

    @app.delete('/api/v1/device/recovery-points/{point_id}')
    def abandon(point_id: str, body: dict, current=Depends(device_auth)):
        grant(current, body.get('assignmentId'), body.get('epoch'), point_run(point_id))
        with storage.lock:
            point = next((p for p in storage.points(point_run(point_id)) if p['pointId'] == point_id))
            if point['status'] == 'READY':
                return {'deleted': False, 'retained': True}
            storage.delete_point(point_id)
        return {'deleted': True}

    def historical(run_id, current):
        body = authorized(run_id, current)
        if not current.get('platformAdmin') or body['status'] != 'COMPLETED':
            raise HTTPException(403, 'Completed experiment and platform administrator required')
        with store.db() as db:
            if db.execute('SELECT 1 FROM assignments WHERE run_id=?', (run_id,)).fetchone():
                raise HTTPException(409, 'Use the assigned coordinator for this experiment')
        return body

    @app.post('/api/v1/experiments/{run_id}/recovery-import')
    def import_begin(run_id: str, body: dict, current=Depends(scoped)):
        experiment = historical(run_id, current)
        if body.get('runId') != run_id or body.get('final') is not True or body.get('childWeightsSha256') != experiment.get('modelVersion'):
            raise HTTPException(422, 'Imported point disagrees with the historical final checkpoint')
        try:
            result = storage.begin(body)
        except (ValueError, QuotaExceeded) as error:
            storage_error(error)
        with store.db() as db:
            store.audit(db, current['userId'], 'HISTORICAL_RECOVERY_IMPORT', body['pointId'], experiment['workspaceId'])
        return result

    @app.post('/api/v1/experiments/{run_id}/recovery-import/complete-object')
    def import_complete(run_id: str, body: dict, current=Depends(scoped)):
        historical(run_id, current)
        if point_run(body.get('pointId')) != run_id:
            raise HTTPException(403, 'Recovery point belongs to another experiment')
        try:
            storage.complete_object(body['pointId'], body['sha256'], body.get('parts', []))
        except (ValueError, QuotaExceeded) as error:
            storage_error(error)
        return {'ok': True}

    @app.post('/api/v1/experiments/{run_id}/recovery-import/{point_id}/verify')
    def import_verify(run_id: str, point_id: str, current=Depends(scoped)):
        historical(run_id, current)
        if point_run(point_id) != run_id:
            raise HTTPException(403, 'Recovery point belongs to another experiment')
        storage.verify_background(point_id)
        return {'status': 'VERIFYING'}

    @app.get('/api/v1/experiments/{run_id}/recovery-points')
    def points(run_id: str, current=Depends(scoped)):
        authorized(run_id, current)
        return storage.points(run_id)

    @app.post('/api/v1/recovery-points/{point_id}/download-plan')
    def download_plan(point_id: str, current=Depends(scoped)):
        authorized(point_run(point_id), current)
        try:
            m = storage.manifest(point_id)
        except ValueError:
            raise HTTPException(409, 'Recovery point is not verified') from None
        return {'manifest': m, 'objects': {name: storage.backend.download_url('objects/' + meta['sha256']) for name, meta in m['files'].items()}}

    @app.delete('/api/v1/recovery-points/{point_id}')
    def delete(point_id: str, current=Depends(scoped)):
        body = authorized(point_run(point_id), current)
        storage.delete_point(point_id)
        with store.db() as db:
            store.audit(db, current['userId'], 'CLOUD_COPY_DELETED', point_id, body['workspaceId'])
        return {'deleted': True}
    with store.db() as db:
        initialize_recovery_schema(db)

    @app.post('/api/v1/artifacts/{artifact_id}/download-ticket')
    def ticket(artifact_id: str, response: Response, request: Request, current=Depends(scoped)):
        run_id, _, name = artifact_id.partition('.')
        authorized(run_id, current)
        if not re.fullmatch('[a-f0-9]{64}\\.bin', name):
            raise HTTPException(404, 'Cloud checkpoint not found')
        sha = name[:-4]
        found = False
        for point in storage.points(run_id):
            if point['status'] == 'READY' and any((v['sha256'] == sha for v in storage.manifest(point['pointId'])['files'].values())):
                found = True
                break
        if not found:
            raise HTTPException(404, 'Cloud checkpoint not ready')
        secret = secrets.token_urlsafe(32)
        td = hashlib.sha256(secret.encode()).hexdigest()
        session_digest = hashlib.sha256(request.headers.get('Authorization', '')[7:].encode()).hexdigest()
        path = '/api/v1/cloud-downloads/' + td
        with store.db() as db:
            db.execute('INSERT INTO cloud_downloads VALUES (?,?,?,?,?,?)', (td, current['userId'], session_digest, run_id, sha, time.time() + 60))
        response.set_cookie('heteroes-cloud-download', secret, httponly=True, secure=request.url.scheme == 'https', samesite='strict', path=path, max_age=60)
        return {'downloadUrl': path}

    @app.get('/api/v1/cloud-downloads/{ticket_digest}')
    def consume(ticket_digest: str, request: Request):
        secret = request.cookies.get('heteroes-cloud-download', '')
        if hashlib.sha256(secret.encode()).hexdigest() != ticket_digest:
            raise HTTPException(401, 'Download ticket required')
        with store.db() as db:
            row = db.execute('SELECT * FROM cloud_downloads WHERE digest=? AND expires>?', (ticket_digest, time.time())).fetchone()
            if not row:
                raise HTTPException(401, 'Download ticket expired')
            if not db.execute('SELECT 1 FROM sessions WHERE digest=? AND user_id=? AND expires>?', (row['session_digest'], row['user_id'], time.time())).fetchone():
                raise HTTPException(401, 'Session revoked')
            body = store.get(row['run_id'])
            profile = store.profile(row['user_id'])
            membership = db.execute('SELECT role FROM memberships WHERE workspace_id=? AND user_id=?', (body['workspaceId'], row['user_id'])).fetchone()
            if profile['accountStatus'] != 'ACTIVE' or not membership or (membership[0] != 'ADMIN' and body['ownerUserId'] != row['user_id']):
                raise HTTPException(403, 'Experiment access revoked')
            db.execute('DELETE FROM cloud_downloads WHERE digest=?', (ticket_digest,))
        response = RedirectResponse(storage.backend.download_url('objects/' + row['sha']), status_code=303)
        response.delete_cookie('heteroes-cloud-download', path='/api/v1/cloud-downloads/' + ticket_digest)
        response.headers['Referrer-Policy'] = 'no-referrer'
        return response
