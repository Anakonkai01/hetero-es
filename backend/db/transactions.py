"""Explicit legacy write boundaries, centralized before the engine migration."""


def begin_write(db):
    return db.execute("BEGIN IMMEDIATE")
