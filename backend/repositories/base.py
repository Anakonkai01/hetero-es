"""Driver error translation shared by domain repositories."""

import sqlite3

from ..core.errors import DatabaseConflict


def execute(db, statement, parameters=()):
    try:
        return db.execute(statement, parameters)
    except sqlite3.IntegrityError:
        raise DatabaseConflict from None
