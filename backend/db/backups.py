"""Consistent SQLite snapshots; metadata publication policy belongs to services."""

import sqlite3


def backup_sqlite(store, database):
    if store.database.dialect != "sqlite":
        raise RuntimeError("PostgreSQL metadata requires the pg_dump backup path")
    # A separate read connection takes a consistent committed snapshot. Backing up the writer connection itself
    # while it owns BEGIN IMMEDIATE would wait indefinitely for its own transaction.
    with sqlite3.connect(store.database.url.database) as source, sqlite3.connect(database) as destination:
        source.backup(destination)
