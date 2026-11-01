"""Consistent SQLite snapshots; metadata publication policy belongs to services."""

import sqlite3


def backup_sqlite(store, database):
    with store.db() as source, sqlite3.connect(database) as destination:
        source.backup(destination)
