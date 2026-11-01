"""Account and session SQL. Transaction ownership belongs to the calling service."""

import sqlite3


class AccountExists(Exception):
    pass


class AccountsRepository:
    @staticmethod
    def by_username(db, username):
        return db.execute(
            "SELECT id,hash,profile FROM users WHERE json_extract(profile,'$.username')=?", (username,)
        ).fetchone()

    @staticmethod
    def profile(db, user_id):
        return db.execute("SELECT profile FROM users WHERE id=?", (user_id,)).fetchone()

    @staticmethod
    def current_session(db, digest, now):
        return db.execute(
            "SELECT users.profile FROM sessions JOIN users ON users.id=sessions.user_id WHERE digest=? AND expires>?",
            (digest, now),
        ).fetchone()

    @staticmethod
    def add_session(db, digest, user_id, expires):
        db.execute("INSERT INTO sessions VALUES (?,?,?)", (digest, user_id, expires))

    @staticmethod
    def delete_session(db, digest):
        db.execute("DELETE FROM sessions WHERE digest=?", (digest,))

    @staticmethod
    def add_user(db, user_id, password_hash, profile):
        try:
            db.execute("INSERT INTO users VALUES (?,?,?)", (user_id, password_hash, profile))
        except sqlite3.IntegrityError:
            raise AccountExists from None

    @staticmethod
    def save_profile(db, user_id, profile):
        db.execute("UPDATE users SET profile=? WHERE id=?", (profile, user_id))

    @staticmethod
    def password_hash(db, user_id):
        return db.execute("SELECT hash FROM users WHERE id=?", (user_id,)).fetchone()[0]

    @staticmethod
    def save_password(db, user_id, password_hash):
        db.execute("UPDATE users SET hash=? WHERE id=?", (password_hash, user_id))

    @staticmethod
    def revoke_other_sessions(db, user_id, digest):
        db.execute("DELETE FROM sessions WHERE user_id=? AND digest<>?", (user_id, digest))
