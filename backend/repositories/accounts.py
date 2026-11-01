"""Account and session SQL. Transaction ownership belongs to the calling service."""

from ..db.dialect import json_text
import sqlite3
from sqlalchemy.exc import IntegrityError


class AccountExists(Exception):
    pass


class AccountsRepository:
    @staticmethod
    def by_username(db, username):
        return db.execute(
            f"SELECT id,hash,profile FROM users WHERE {json_text(db, 'profile', 'username')}=:p0", (username,)
        ).fetchone()

    @staticmethod
    def profile(db, user_id):
        return db.execute("SELECT profile FROM users WHERE id=:p0", (user_id,)).fetchone()

    @staticmethod
    def current_session(db, digest, now):
        return db.execute(
            "SELECT users.profile FROM sessions JOIN users ON users.id=sessions.user_id WHERE digest=:p0 AND expires>:p1",
            (digest, now),
        ).fetchone()

    @staticmethod
    def add_session(db, digest, user_id, expires):
        db.execute("INSERT INTO sessions(digest,user_id,expires)  VALUES (:p0,:p1,:p2)", (digest, user_id, expires))

    @staticmethod
    def delete_session(db, digest):
        db.execute("DELETE FROM sessions WHERE digest=:p0", (digest,))

    @staticmethod
    def delete_download_tickets(db, digest):
        db.execute("DELETE FROM cloud_downloads WHERE session_digest=:p0", (digest,))

    @staticmethod
    def bootstrap_membership(db, user_id):
        db.execute(
            "INSERT INTO memberships(workspace_id,user_id,role) VALUES ('lab',:p0,'ADMIN') ON CONFLICT DO NOTHING",
            (user_id,),
        )

    @staticmethod
    def add_user(db, user_id, password_hash, profile):
        try:
            db.execute("INSERT INTO users(id,hash,profile)  VALUES (:p0,:p1,:p2)", (user_id, password_hash, profile))
        except (sqlite3.IntegrityError, IntegrityError):
            raise AccountExists from None

    @staticmethod
    def save_profile(db, user_id, profile):
        db.execute("UPDATE users SET profile=:p0 WHERE id=:p1", (profile, user_id))

    @staticmethod
    def password_hash(db, user_id):
        return db.execute("SELECT hash FROM users WHERE id=:p0", (user_id,)).fetchone()[0]

    @staticmethod
    def save_password(db, user_id, password_hash):
        db.execute("UPDATE users SET hash=:p0 WHERE id=:p1", (password_hash, user_id))

    @staticmethod
    def revoke_other_sessions(db, user_id, digest):
        db.execute("DELETE FROM sessions WHERE user_id=:p0 AND digest<>:p1", (user_id, digest))
