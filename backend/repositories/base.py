"""Driver error translation shared by domain repositories."""

import sqlite3
from sqlalchemy.exc import IntegrityError

from ..core.errors import DatabaseConflict
from ..db.bindings import bind_parameters


def execute(db, statement, parameters=()):
    try:
        sql, bindings = bind_parameters(statement, parameters)
        return db.execute(sql, bindings)
    except (sqlite3.IntegrityError, IntegrityError):
        raise DatabaseConflict from None
