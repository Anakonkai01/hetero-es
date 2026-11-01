"""Local account/session policy. HTTP parsing and response construction stay in api/."""

import hashlib
import json
import secrets
import time
import uuid

from argon2.exceptions import InvalidHashError, VerificationError

from ..core.errors import ServiceError
from ..passwords import password_problem
from ..repositories.accounts import AccountExists, AccountsRepository


def _digest(token):
    return hashlib.sha256(token.encode()).hexdigest()


class AccountService:
    mode = "local"

    def __init__(self, store):
        self.store = store
        self.repository = AccountsRepository()

    def profile(self, user_id):
        with self.store.db() as db:
            row = self.repository.profile(db, user_id)
            return json.loads(row[0]) if row else None

    def current(self, token):
        with self.store.db() as db:
            row = self.repository.current_session(db, _digest(token), time.time())
        if not row:
            raise ServiceError(401, "Session expired or revoked")
        return json.loads(row[0])

    def session(self, current):
        return {
            "user": current,
            "workspaces": self.store.workspaces(current["userId"]) if current["accountStatus"] == "ACTIVE" else [],
        }

    def authenticate(self, username, password, session):
        with self.store.db() as db:
            row = self.repository.by_username(db, username)
            try:
                self.store.hasher.verify(row["hash"] if row else self.store.hasher.hash("unknown-user"), password)
            except (InvalidHashError, VerificationError):
                raise ServiceError(401, "Invalid username or password") from None
            if not row:
                raise ServiceError(401, "Invalid username or password")
            token = secrets.token_urlsafe(32)
            self.repository.add_session(db, _digest(token), row["id"], time.time() + 43200)
            return {**session(json.loads(row["profile"])), "accessToken": token}

    def sign_in(self, username, password, address, failures, failures_by_address, session):
        key = (address, username.lower())
        wait = max(failures.retry_after(key), failures_by_address.retry_after(address))
        if wait:
            raise ServiceError(
                429, f"Too many attempts. Try again in {wait} seconds.", headers={"Retry-After": str(wait)}
            )
        try:
            result = self.authenticate(username, password, session)
        except ServiceError as error:
            if error.status_code == 401:
                failures.record(key)
                failures_by_address.record(address)
            raise
        failures.clear(key)
        return result

    def sign_out(self, token):
        with self.store.db() as db:
            self.repository.delete_session(db, _digest(token))

    def download_session(self, token, user_id):
        return _digest(token), time.time() + 60

    @staticmethod
    def external_download_session(digest):
        return False

    def register(self, username, password, display_name, address, registrations):
        wait = registrations.retry_after(address)
        if wait:
            raise ServiceError(
                429,
                f"Too many registrations from this address. Try again in {wait} seconds.",
                headers={"Retry-After": str(wait)},
            )
        problem = password_problem(password, username, display_name)
        if problem:
            raise ServiceError(422, problem)
        registrations.record(address)
        profile = {
            "userId": uuid.uuid4().hex,
            "username": username,
            "displayName": display_name,
            "accountStatus": "PENDING",
            "platformAdmin": False,
            "canCreateWorkspace": False,
        }
        with self.store.db() as db:
            try:
                self.repository.add_user(db, profile["userId"], self.store.hasher.hash(password), json.dumps(profile))
            except AccountExists:
                raise ServiceError(409, "Username already exists") from None
            self.store.audit(db, profile["userId"], "REGISTER", profile["userId"])
        return profile

    def edit_profile(self, user_id, changes):
        with self.store.db() as db:
            profile = self.store.profile(user_id)
            profile.update(changes)
            self.repository.save_profile(db, user_id, json.dumps(profile))
            self.store.audit(db, user_id, "PROFILE_EDIT", user_id)
            return profile

    def change_password(self, user_id, current_password, new_password, token):
        profile = self.store.profile(user_id)
        problem = password_problem(new_password, profile["username"], profile.get("displayName", ""))
        if problem:
            raise ServiceError(422, problem)
        with self.store.db() as db:
            password_hash = self.repository.password_hash(db, user_id)
            try:
                self.store.hasher.verify(password_hash, current_password)
            except VerificationError:
                raise ServiceError(403, "Current password is incorrect") from None
            self.repository.save_password(db, user_id, self.store.hasher.hash(new_password))
            self.repository.revoke_other_sessions(db, user_id, _digest(token))
            self.store.audit(db, user_id, "PASSWORD_CHANGE", user_id)

    def revoke_other_sessions(self, user_id, token):
        with self.store.db() as db:
            self.repository.revoke_other_sessions(db, user_id, _digest(token))
            self.store.audit(db, user_id, "REVOKE_OTHER_SESSIONS", user_id)
