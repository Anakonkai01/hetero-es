"""Explicit legacy write boundaries, centralized before the engine migration."""


def begin_write(db):
    if hasattr(db, "begin_write"):
        return db.begin_write()
    return db.execute("BEGIN IMMEDIATE")
