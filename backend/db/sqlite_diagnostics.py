"""SQLite operational diagnostics and driver boundary."""

import sqlite3
from ..repositories.base import execute

DatabaseError = sqlite3.Error
DatabaseCorruption = sqlite3.DatabaseError


def connect_readonly(*args, **kwargs):
    return sqlite3.connect(*args, **kwargs)


class SQLiteDiagnostics:
    @staticmethod
    def deployment_idle_1(db, parameters=(), *, table):
        return execute(db, f"SELECT count(*) FROM {table}", parameters)

    @staticmethod
    def doctor_run_checks_2(db, parameters=()):
        return execute(db, "SELECT 1 FROM sqlite_master WHERE name='devices'", parameters)

    @staticmethod
    def doctor_run_checks_3(db, parameters=()):
        return execute(db, "PRAGMA user_version", parameters)

    @staticmethod
    def doctor_run_checks_4(db, parameters=()):
        return execute(db, "SELECT 1 FROM sqlite_master WHERE name='physical_reservations'", parameters)

    @staticmethod
    def doctor_run_checks_5(db, parameters=()):
        return execute(db, "SELECT status, seen FROM devices", parameters)

    @staticmethod
    def doctor_run_checks_6(db, parameters=()):
        return execute(db, "PRAGMA integrity_check", parameters)

    @staticmethod
    def doctor_run_checks_7(db, parameters=()):
        return execute(db, "SELECT count(*) FROM physical_reservations", parameters)
