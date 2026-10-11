"""Identity and membership operations, independent of runtime numerical state."""
import hashlib
import json
import sqlite3
import secrets
import time
import uuid
from typing import Literal

from argon2.exceptions import VerificationError
from fastapi import Cookie, Depends, Header, HTTPException, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field

from .store import ACTIVE, now
from .backup import begin_maintenance,end_maintenance,create_bundle,bundle_path


class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid')


class Registration(Strict):
    username: str = Field(min_length=3,max_length=64,pattern=r'^[a-zA-Z0-9][a-zA-Z0-9_.-]*$')
    password: str = Field(min_length=12,max_length=200)
    displayName: str = Field(min_length=1,max_length=100)


class ProfileEdit(Strict):
    displayName: str | None = Field(default=None,min_length=1,max_length=100)
    email: str | None = Field(default=None,max_length=200)
    bio: str | None = Field(default=None,max_length=1000)


class AccountEdit(Strict):
    accountStatus: Literal['PENDING','ACTIVE','REJECTED','SUSPENDED'] | None = None
    canCreateWorkspace: bool | None = None
    platformAdmin: bool | None = None


class PasswordEdit(Strict):
    currentPassword: str = Field(max_length=200)
    newPassword: str = Field(min_length=12,max_length=200)


class WorkspaceCreate(Strict):
    name: str = Field(min_length=3,max_length=100)
    description: str = Field(default='',max_length=1000)


class Invite(Strict):
    username: str = Field(min_length=3,max_length=64)


class MemberEdit(Strict):
    role: Literal['ADMIN','PARTICIPANT']


class Contribution(Strict):
    enabled: bool
    workspaceId: str | None = None
    ownerUserId: str | None = None


class Resume(Strict):
    workerConfigurationConfirmed: Literal[True]


def install_lab_routes(app, store, user, scoped, runtime):
    def active(current=Depends(user)):
        profile=store.profile(current['userId'])
        if profile['accountStatus']!='ACTIVE':
            raise HTTPException(403,'Your account is awaiting approval or is restricted')
        return profile

    def platform(current=Depends(active)):
        if not current.get('platformAdmin'):
            raise HTTPException(403,'Platform administrator permission required')
        return current

    def workspace_admin(workspace_id,current):
        fresh = scoped(current,workspace_id)
        if fresh['workspaceRole']!='ADMIN':
            raise HTTPException(403,'Workspace administrator permission required')
        return fresh

    @app.post('/api/v1/auth/register',status_code=201)
    def register(body:Registration):
        profile={'userId':uuid.uuid4().hex,'username':body.username,'displayName':body.displayName,
                 'accountStatus':'PENDING','platformAdmin':False,'canCreateWorkspace':False}
        with store.db() as db:
            try:
                db.execute('INSERT INTO users VALUES (?,?,?)',(profile['userId'],store.hasher.hash(body.password),json.dumps(profile)))
            except sqlite3.IntegrityError:
                raise HTTPException(409,'Username already exists') from None
            store.audit(db,profile['userId'],'REGISTER',profile['userId'])
        return profile

    @app.patch('/api/v1/profile')
    def edit_profile(body:ProfileEdit,current=Depends(user)):
        with store.db() as db:
            profile=store.profile(current['userId'])
            profile.update(body.model_dump(exclude_none=True))
            db.execute('UPDATE users SET profile=? WHERE id=?',(json.dumps(profile),current['userId']))
            store.audit(db,current['userId'],'PROFILE_EDIT',current['userId'])
            return profile

    @app.post('/api/v1/auth/password',status_code=204)
    def change_password(body:PasswordEdit,current=Depends(user),authorization:str=Header()):
        with store.db() as db:
            password_hash=db.execute('SELECT hash FROM users WHERE id=?',(current['userId'],)).fetchone()[0]
            try:
                store.hasher.verify(password_hash,body.currentPassword)
            except VerificationError:
                raise HTTPException(403,'Current password is incorrect') from None
            db.execute('UPDATE users SET hash=? WHERE id=?',(store.hasher.hash(body.newPassword),current['userId']))
            digest=hashlib.sha256(authorization[7:].encode()).hexdigest()
            db.execute('DELETE FROM sessions WHERE user_id=? AND digest<>?',(current['userId'],digest))
            store.audit(db,current['userId'],'PASSWORD_CHANGE',current['userId'])
        return Response(status_code=204)

    @app.post('/api/v1/auth/revoke-other-sessions',status_code=204)
    def revoke_other_sessions(current=Depends(user),authorization:str=Header()):
        with store.db() as db:
            db.execute('DELETE FROM sessions WHERE user_id=? AND digest<>?',
                       (current['userId'],hashlib.sha256(authorization[7:].encode()).hexdigest()))
            store.audit(db,current['userId'],'REVOKE_OTHER_SESSIONS',current['userId'])
        return Response(status_code=204)

    @app.get('/api/v1/platform/users')
    def users(current=Depends(platform)):
        with store.db() as db:
            return [json.loads(r[0]) for r in db.execute('SELECT profile FROM users ORDER BY rowid')]

    @app.patch('/api/v1/platform/users/{user_id}')
    def edit_account(user_id:str,body:AccountEdit,current=Depends(platform)):
        with store.db() as db:
            platform(current)
            old=store.profile(user_id)
            if not old:
                raise HTTPException(404,'Account not found')
            updated={**old,**body.model_dump(exclude_none=True)}
            if old.get('platformAdmin') and (not updated['platformAdmin'] or updated['accountStatus']!='ACTIVE'):
                others=[json.loads(r[0]) for r in db.execute('SELECT profile FROM users WHERE id<>?',(user_id,))]
                if not any(p.get('platformAdmin') and p['accountStatus']=='ACTIVE' for p in others):
                    raise HTTPException(409,'Keep at least one active platform administrator')
            db.execute('UPDATE users SET profile=? WHERE id=?',(json.dumps(updated),user_id))
            if updated['accountStatus']!='ACTIVE':
                db.execute('DELETE FROM sessions WHERE user_id=?',(user_id,))
                store.cancel_owned(db,user_id)
                disabled=store.disabled_workers(db)
                for r in db.execute('SELECT worker_id FROM worker_assignments WHERE owner=?',(user_id,)).fetchall():
                    disabled.add(r[0]);store.cancel_selected(db,r[0])
                db.execute('INSERT OR REPLACE INTO settings VALUES (?,?)',('disabledWorkers',json.dumps(sorted(disabled))))
            store.audit(db,current['userId'],'ACCOUNT_UPDATE',user_id)
            return updated

    @app.post('/api/v1/platform/users/{user_id}/revoke-sessions',status_code=204)
    def revoke_sessions(user_id:str,current=Depends(platform)):
        with store.db() as db:
            platform(current)
            if not store.profile(user_id):
                raise HTTPException(404,'Account not found')
            db.execute('DELETE FROM sessions WHERE user_id=?',(user_id,))
            store.audit(db,current['userId'],'REVOKE_SESSIONS',user_id)
        return Response(status_code=204)

    @app.post('/api/v1/workspaces',status_code=201)
    def create_workspace(body:WorkspaceCreate,current=Depends(active)):
        with store.db() as db:
            current=active(current)
            if not current.get('canCreateWorkspace'):
                raise HTTPException(403,'Workspace creation permission required')
            wid=uuid.uuid4().hex
            db.execute('INSERT INTO workspaces VALUES (?,?,?,?)',(wid,body.name,body.description,current['userId']))
            db.execute('INSERT INTO memberships VALUES (?,?,?)',(wid,current['userId'],'ADMIN'))
            store.audit(db,current['userId'],'WORKSPACE_CREATE',wid,wid)
            return {'workspaceId':wid,'name':body.name,'description':body.description,'creatorUserId':current['userId'],'role':'ADMIN'}

    @app.post('/api/v1/workspaces/{workspace_id}/invitations',status_code=201)
    def invite(workspace_id:str,body:Invite,current=Depends(active)):
        with store.db() as db:
            workspace_admin(workspace_id,current)
            target=db.execute("SELECT id,profile FROM users WHERE json_extract(profile,'$.username')=?",(body.username,)).fetchone()
            if not target or json.loads(target['profile'])['accountStatus']!='ACTIVE':
                raise HTTPException(422,'Invite an approved account by username')
            if db.execute('SELECT 1 FROM memberships WHERE workspace_id=? AND user_id=?',(workspace_id,target['id'])).fetchone():
                raise HTTPException(409,'Account is already a member')
            iid=uuid.uuid4().hex
            try:
                db.execute('INSERT INTO invitations VALUES (?,?,?,?,?)',(iid,workspace_id,target['id'],'PENDING',now()))
            except sqlite3.IntegrityError:
                raise HTTPException(409,'A pending invitation already exists') from None
            store.audit(db,current['userId'],'INVITE',target['id'],workspace_id)
            return {'invitationId':iid,'workspaceId':workspace_id,'username':body.username,'status':'PENDING'}

    @app.get('/api/v1/my-invitations')
    def invitations(current=Depends(active)):
        with store.db() as db:
            return [{'invitationId':r['id'],'workspaceId':r['workspace_id'],'workspaceName':r['name'],
                     'username':current['username'],'email':'','status':r['status'],'createdAt':r['created']}
                for r in db.execute('SELECT i.*,w.name FROM invitations i JOIN workspaces w ON w.id=i.workspace_id WHERE i.user_id=? AND i.status="PENDING"',(current['userId'],))]

    @app.post('/api/v1/my-invitations/{invitation_id}/accept')
    def accept(invitation_id:str,current=Depends(active)):
        with store.db() as db:
            active(current)
            row=db.execute('SELECT * FROM invitations WHERE id=? AND user_id=?',(invitation_id,current['userId'])).fetchone()
            if not row or row['status']!='PENDING':
                raise HTTPException(404,'Pending invitation not found')
            db.execute('INSERT OR IGNORE INTO memberships VALUES (?,?,?)',(row['workspace_id'],current['userId'],'PARTICIPANT'))
            db.execute('UPDATE invitations SET status="ACCEPTED" WHERE id=?',(invitation_id,))
            store.audit(db,current['userId'],'INVITATION_ACCEPT',invitation_id,row['workspace_id'])
            return {'invitationId':invitation_id,'workspaceId':row['workspace_id'],'status':'ACCEPTED'}

    def member_change(db,workspace_id,user_id,current,role=None):
        workspace_admin(workspace_id,current)
        old=db.execute('SELECT role FROM memberships WHERE workspace_id=? AND user_id=?',(workspace_id,user_id)).fetchone()
        if not old:
            raise HTTPException(404,'Member not found')
        if old[0]=='ADMIN' and role!='ADMIN':
            others=db.execute("SELECT count(*) FROM memberships m JOIN users u ON u.id=m.user_id WHERE m.workspace_id=? AND m.role='ADMIN' AND m.user_id<>? AND json_extract(u.profile,'$.accountStatus')='ACTIVE'",(workspace_id,user_id)).fetchone()[0]
            if others==0:
                raise HTTPException(409,'Keep at least one workspace administrator')
        if role:
            db.execute('UPDATE memberships SET role=? WHERE workspace_id=? AND user_id=?',(role,workspace_id,user_id))
        else:
            db.execute('DELETE FROM memberships WHERE workspace_id=? AND user_id=?',(workspace_id,user_id))
            db.execute('UPDATE invitations SET status="REVOKED" WHERE workspace_id=? AND user_id=? AND status="PENDING"',(workspace_id,user_id))
            store.cancel_owned(db,user_id,workspace_id)
            disabled=store.disabled_workers(db)
            for r in db.execute('SELECT worker_id FROM worker_assignments WHERE owner=? AND workspace_id=?',(user_id,workspace_id)).fetchall():
                disabled.add(r[0]);store.cancel_selected(db,r[0])
            db.execute('INSERT OR REPLACE INTO settings VALUES (?,?)',('disabledWorkers',json.dumps(sorted(disabled))))
        store.audit(db,current['userId'],'MEMBER_ROLE' if role else 'MEMBER_REMOVE',user_id,workspace_id)

    @app.patch('/api/v1/workspaces/{workspace_id}/members/{user_id}')
    def change_role(workspace_id:str,user_id:str,body:MemberEdit,current=Depends(active)):
        with store.db() as db:
            member_change(db,workspace_id,user_id,current,body.role)
        return {'userId':user_id,'role':body.role}

    @app.delete('/api/v1/workspaces/{workspace_id}/members/{user_id}',status_code=204)
    def remove_member(workspace_id:str,user_id:str,current=Depends(active)):
        with store.db() as db:
            member_change(db,workspace_id,user_id,current)
        return Response(status_code=204)

    @app.get('/api/v1/queue')
    def queue(current=Depends(scoped)):
        with store.db() as db:
            held=json.loads(db.execute('SELECT value FROM settings WHERE key="dispatchHold"').fetchone()[0])
            positions={r['run_id']:i+1 for i,r in enumerate(db.execute('SELECT run_id FROM queue ORDER BY sequence'))}
            result=[]
            for r in db.execute('SELECT body FROM experiments'):
                b=json.loads(r[0])
                if b['workspaceId']==current['workspaceId'] and b['experimentId'] in positions and (current['workspaceRole']=='ADMIN' or b['ownerUserId']==current['userId']):
                    result.append({'experimentId':b['experimentId'],'position':positions[b['experimentId']],
                                   'reason':'Maintenance hold' if held else b.get('waitingReason','Waiting for runtime release') if b['status']=='QUEUED' else b['status']})
            return result

    @app.get('/api/v1/platform/audit')
    def platform_audit(current=Depends(platform)):
        with store.db() as db:
            return [dict(r) for r in db.execute('SELECT * FROM audit WHERE workspace_id IS NULL ORDER BY sequence DESC LIMIT 200')]

    @app.get('/api/v1/contributions')
    def contributions(current=Depends(active)):
        with store.db() as db:
            disabled=store.disabled_workers(db)
            return [{**dict(r),'enabled':r['worker_id'] not in disabled}
                for r in db.execute('SELECT * FROM worker_assignments')
                if current.get('platformAdmin') or r['owner']==current['userId']]

    @app.post('/api/v1/contributions/{worker_id}')
    def contribution(worker_id:str,body:Contribution,current=Depends(active)):
        with store.operation_lock:
            with store.db() as db:
                if getattr(runtime,'agent_mode',False) and body.ownerUserId:
                    enrolled=db.execute('SELECT owner FROM devices WHERE worker_id=?',(worker_id,)).fetchone()
                    if enrolled and enrolled[0]!=body.ownerUserId:
                        raise HTTPException(409,'Revoke and re-enroll the device before changing its owner')
                current=active(current)
                row=db.execute('SELECT * FROM worker_assignments WHERE worker_id=?',(worker_id,)).fetchone()
                if not row or (not current.get('platformAdmin') and row['owner']!=current['userId']):
                    raise HTTPException(404,'Owned GPU not found')
                if body.ownerUserId and not current.get('platformAdmin'):
                    raise HTTPException(403,'Only a platform administrator can assign GPU ownership')
                owner=body.ownerUserId or row['owner']
                if not store.profile(owner) or store.profile(owner)['accountStatus']!='ACTIVE':
                    raise HTTPException(422,'Select an active GPU owner')
                if not body.enabled:
                    if body.ownerUserId and body.ownerUserId!=row['owner']:
                        raise HTTPException(409,'Change ownership only after confirmed idle shutdown')
                    disabled=store.disabled_workers(db);disabled.add(worker_id)
                    db.execute('INSERT OR REPLACE INTO settings VALUES (?,?)',('disabledWorkers',json.dumps(sorted(disabled))))
                    store.cancel_selected(db,worker_id)
                    store.audit(db,current['userId'],'GPU_CONTRIBUTION_OFF',worker_id,row['workspace_id'])
                    return {'workerId':worker_id,'enabled':False,'workspaceId':row['workspace_id'],'draining':any(
                        b['status'] in ACTIVE and worker_id in b['workerIds'] for b in store.list())}
                if not body.workspaceId:
                    raise HTTPException(422,'Choose the contributing workspace')
                if not db.execute('SELECT 1 FROM memberships WHERE workspace_id=? AND user_id=?',(body.workspaceId,owner)).fetchone():
                    raise HTTPException(422,'The GPU owner must belong to the target workspace')
            # A hold closes the gap between checking idle and committing assignment.
            begin_maintenance(store,current['userId'])
            try:
                with store.db() as db:
                    fresh=active(current)
                    if (not fresh.get('platformAdmin') and row['owner']!=fresh['userId']) or (body.ownerUserId and not fresh.get('platformAdmin')):
                        raise HTTPException(403,'GPU ownership permission changed')
                    owner_profile=store.profile(owner)
                    if owner_profile['accountStatus']!='ACTIVE' or not db.execute('SELECT 1 FROM memberships WHERE workspace_id=? AND user_id=?',(body.workspaceId,owner)).fetchone():
                        raise HTTPException(409,'Target membership changed during maintenance')
                    db.execute('UPDATE worker_assignments SET owner=?,workspace_id=? WHERE worker_id=?',(owner,body.workspaceId,worker_id))
                    disabled=store.disabled_workers(db);disabled.discard(worker_id)
                    db.execute('INSERT OR REPLACE INTO settings VALUES (?,?)',('disabledWorkers',json.dumps(sorted(disabled))))
                    store.audit(db,current['userId'],'GPU_CONTRIBUTION_ON',worker_id,body.workspaceId)
                end_maintenance(store,current['userId'])
            except BaseException:
                # Keep the deployment held until operator review after an uncertain RPC.
                raise
            return {'workerId':worker_id,'enabled':True,'workspaceId':body.workspaceId,'ownerUserId':owner}

    @app.get('/api/v1/platform/operations')
    def operations(current=Depends(platform)):
        with store.db() as db:
            held=json.loads(db.execute('SELECT value FROM settings WHERE key="dispatchHold"').fetchone()[0])
            queue_count=db.execute('SELECT count(*) FROM queue').fetchone()[0]
            metadata=db.execute('SELECT value FROM settings WHERE key="metadataBackupStatus"').fetchone()
        result={'dispatchHeld':held,'queueCount':queue_count,'runtimeIssue':store.last_error,
                'agentMode':bool(getattr(runtime,'agent_mode',False)),
                'cloudStorageConfigured':getattr(runtime,'storage_backend',None) is not None and getattr(runtime.storage_backend,'mode','cloud')=='cloud',
                'recoveryStorageConfigured':getattr(runtime,'storage_backend',None) is not None,
                'recoveryStorageMode':getattr(runtime.storage_backend,'mode','cloud') if getattr(runtime,'storage_backend',None) is not None else None,
                'metadataBackup':json.loads(metadata[0]) if metadata else None,
                'productService':'ONLINE','runtimeService':'UNAVAILABLE','workers':[],'reservations':[]}
        try:
            cap=runtime.capabilities()
            store.ensure_workers(cap['workerIds'])
            runs=runtime.runs()
            result.update(runtimeService='ONLINE',workers=runtime.workers(),quarantinedWorkerIds=cap.get('quarantinedWorkerIds',[]),
                          reservations=[{'runId':r['runId'],'status':r['status'],'workerStates':r.get('workerStates',{}),
                              'failureReason':r.get('failureReason')} for r in runs if r['status'] in ACTIVE],
                          recentFailures=[{'runId':r['runId'],'status':r['status'],'failureReason':r.get('failureReason')}
                              for r in sorted(runs,key=lambda r:r.get('startedAt',0),reverse=True) if r.get('failureReason')][:20],
                          runtimeMaintenance=bool(runtime.maintenance()))
        except Exception as error:
            result['runtimeIssue']=type(error).__name__
        result['assignments']=contributions(current)
        return result

    @app.post('/api/v1/platform/maintenance/resume')
    def resume(body:Resume,current=Depends(platform)):
        with store.operation_lock:
            platform(current)
            cap=runtime.capabilities()
            with store.db() as db:
                selected={wid for b in store.list() if b['status']=='QUEUED' for wid in b['workerIds']}
                if not selected<=set(cap['workerIds']):
                    raise HTTPException(409,'Configure all imported queued worker IDs or cancel their queued experiments before resuming')
            end_maintenance(store,current['userId'])
        return {'dispatchHeld':False}

    @app.post('/api/v1/platform/backups',status_code=201)
    def backup(current=Depends(platform)):
        if getattr(runtime,'agent_mode',False):
            raise HTTPException(409,'Use experiment recovery points and product metadata backups in agent mode')
        with store.operation_lock:
            platform(current)
            return create_bundle(store,current['userId'])

    @app.get('/api/v1/platform/backups')
    def backups(current=Depends(platform)):
        from pathlib import Path
        return [{'backupId':p.stem,'sizeBytes':p.stat().st_size} for p in sorted((Path(store.path).parent/'backups').glob('*.tar'))]

    @app.get('/api/v1/platform/backups/{backup_id}/download')
    def download_backup(backup_id:str,authorization:str=Header(default=''),
                        ticket:str=Cookie(default='',alias='heteroes-backup-download')):
        with store.db() as db:
            if authorization:
                current=platform(user(authorization))
            else:
                key='backupDownload:'+hashlib.sha256(ticket.encode()).hexdigest()
                row=db.execute('SELECT value FROM settings WHERE key=?',(key,)).fetchone()
                grant=json.loads(row[0]) if row else {}
                session_row=db.execute('SELECT user_id FROM sessions WHERE digest=? AND expires>?',
                    (grant.get('sessionDigest',''),time.time())).fetchone()
                if grant.get('backupId')!=backup_id or grant.get('expires',0)<time.time() or not session_row:
                    raise HTTPException(401,'Backup download authorization expired')
                current=platform(store.profile(session_row['user_id']))
                db.execute('DELETE FROM settings WHERE key=?',(key,))
            store.audit(db,current['userId'],'BACKUP_DOWNLOAD',backup_id)
        return FileResponse(bundle_path(store,backup_id),media_type='application/x-tar',filename='heteroes-lab-'+backup_id+'.tar')

    @app.post('/api/v1/platform/backups/{backup_id}/download-ticket')
    def download_ticket(backup_id:str,response:Response,current=Depends(platform),authorization:str=Header()):
        bundle_path(store,backup_id)
        ticket=secrets.token_urlsafe(32)
        path=f'/api/v1/platform/backups/{backup_id}/download'
        with store.db() as db:
            platform(current)
            db.execute('INSERT INTO settings VALUES (?,?)',('backupDownload:'+hashlib.sha256(ticket.encode()).hexdigest(),
                json.dumps({'backupId':backup_id,'expires':time.time()+60,'sessionDigest':hashlib.sha256(authorization[7:].encode()).hexdigest()})))
            store.audit(db,current['userId'],'BACKUP_DOWNLOAD_AUTHORIZE',backup_id)
        # Scoped one-use cookie allows a native browser download stream instead
        # of materializing a many-gigabyte backup in JavaScript memory.
        response.set_cookie('heteroes-backup-download',ticket,max_age=60,httponly=True,samesite='strict',path=path)
        return {'downloadUrl':path}
