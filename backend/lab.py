"""Identity and membership operations, independent of runtime numerical state."""
import hashlib
import json
import sqlite3
import uuid
from typing import Literal

from argon2.exceptions import VerificationError
from fastapi import Depends, Header, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from .store import ACTIVE, now
from .throttle import client_address
from .passwords import password_problem


class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid')


class Registration(Strict):
    username: str = Field(min_length=3,max_length=64,pattern=r'^[a-zA-Z0-9][a-zA-Z0-9_.-]*$')
    password: str = Field(max_length=200)
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
    newPassword: str = Field(max_length=200)


class WorkspaceCreate(Strict):
    name: str = Field(min_length=3,max_length=100)
    description: str = Field(default='',max_length=1000)


class Invite(Strict):
    username: str = Field(min_length=3,max_length=64)


class MemberEdit(Strict):
    role: Literal['ADMIN','PARTICIPANT']


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
    def register(body:Registration,request:Request):
        address=client_address(request.client.host if request.client else None,request.headers)
        wait=app.state.registrations.retry_after(address)
        if wait:
            raise HTTPException(429,f'Too many registrations from this address. Try again in {wait} seconds.',headers={'Retry-After':str(wait)})
        problem=password_problem(body.password,body.username,body.displayName)
        if problem:
            raise HTTPException(422,problem)
        app.state.registrations.record(address)
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
        profile=store.profile(current['userId'])
        problem=password_problem(body.newPassword,profile['username'],profile.get('displayName',''))
        if problem:
            raise HTTPException(422,problem)
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

    @app.get('/api/v1/platform/operations')
    def operations(current=Depends(platform)):
        with store.db() as db:
            held=json.loads(db.execute('SELECT value FROM settings WHERE key="dispatchHold"').fetchone()[0])
            queue_count=db.execute('SELECT count(*) FROM queue').fetchone()[0]
            metadata=db.execute('SELECT value FROM settings WHERE key="metadataBackupStatus"').fetchone()
        result={'dispatchHeld':held,'queueCount':queue_count,'runtimeIssue':store.last_error,
                'cloudStorageConfigured':False,
                'recoveryStorageConfigured':getattr(runtime,'storage_backend',None) is not None,
                'recoveryStorageMode':getattr(runtime.storage_backend,'mode','local') if getattr(runtime,'storage_backend',None) is not None else None,
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
                              for r in sorted(runs,key=lambda r:r.get('startedAt',0),reverse=True) if r.get('failureReason')][:20])
        except Exception as error:
            result['runtimeIssue']=type(error).__name__
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
                db.execute('UPDATE settings SET value="false" WHERE key="dispatchHold"')
                # Holds left by the removed M1 maintenance (begin_maintenance) are cleared too.
                db.execute('DELETE FROM settings WHERE key IN ("maintenanceId","agentMaintenance")')
                store.audit(db,current['userId'],'MAINTENANCE_END','deployment')
        return {'dispatchHeld':False}
