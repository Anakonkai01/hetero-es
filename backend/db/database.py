"""SQLite connection and bootstrap ownership; runtime ledgers stay independent."""

from contextlib import contextmanager
import json
import sqlite3
from .migrations import initialize_product_schema, initialize_workspace_extras, migrate


class SQLiteDatabase:
    def __init__(self, path, lock):
        self.path, self.lock = str(path), lock

    def initialize(self, passwords, hasher):
        with self.connection() as db:
            initialize_product_schema(db)
            for name, password in passwords.items():
                profile = {"userId": name, "username": name, "displayName": name.title(), "canCreateWorkspace": False}
                # Bootstrap secrets seed an empty installation only. A renamed
                # or removed account must not be recreated on every restart.
                if db.execute("PRAGMA user_version").fetchone()[0] == 0:
                    db.execute(
                        "INSERT OR IGNORE INTO users VALUES (?,?,?)",
                        (name, hasher.hash(password), json.dumps(profile)),
                    )
            db.commit()
            migrate(db)
            initialize_workspace_extras(db)

    @contextmanager
    def connection(self):
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
