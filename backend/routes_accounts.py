"""Identity and membership operations, independent of runtime numerical state."""
from .request_models import Registration, ProfileEdit, PasswordEdit
import hashlib
import json
import sqlite3
import uuid

from argon2.exceptions import VerificationError
from fastapi import Depends, Header, HTTPException, Request, Response

from .throttle import client_address
from .passwords import password_problem





















from fastapi import APIRouter


def install_routes(app, store, user):
    router = APIRouter()
    @router.post('/api/v1/auth/register',status_code=201)
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

    @router.patch('/api/v1/profile')
    def edit_profile(body:ProfileEdit,current=Depends(user)):
        with store.db() as db:
            profile=store.profile(current['userId'])
            profile.update(body.model_dump(exclude_none=True))
            db.execute('UPDATE users SET profile=? WHERE id=?',(json.dumps(profile),current['userId']))
            store.audit(db,current['userId'],'PROFILE_EDIT',current['userId'])
            return profile

    @router.post('/api/v1/auth/password',status_code=204)
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

    @router.post('/api/v1/auth/revoke-other-sessions',status_code=204)
    def revoke_other_sessions(current=Depends(user),authorization:str=Header()):
        with store.db() as db:
            db.execute('DELETE FROM sessions WHERE user_id=? AND digest<>?',
                       (current['userId'],hashlib.sha256(authorization[7:].encode()).hexdigest()))
            store.audit(db,current['userId'],'REVOKE_OTHER_SESSIONS',current['userId'])
        return Response(status_code=204)

    app.include_router(router)
