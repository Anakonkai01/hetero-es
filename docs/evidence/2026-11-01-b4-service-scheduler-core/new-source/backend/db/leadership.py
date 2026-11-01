"""One dedicated PostgreSQL scheduler session; ticks commit only through that owning physical connection."""

from contextlib import contextmanager

from sqlalchemy import text

# Session leadership and lab write transactions must never contend on the same key.
SCHEDULER_LOCK = 0x4845534348454431


class SchedulerLeadershipLost(RuntimeError):
    pass


class SchedulerLeader:
    def __init__(self, database):
        if database.dialect != "postgresql":
            raise ValueError("Distributed scheduler leadership requires PostgreSQL")
        self.database = database
        self._connection, self._held, self.backend_pid = None, False, None

    @property
    def held(self):
        return self._held

    def try_acquire(self):
        if self._held:
            return self.heartbeat()
        connection = self.database.engine.connect()
        self._connection = connection
        try:
            # Returning a session advisory lock to a pool is not a release. This connection closes on cleanup.
            connection.detach()
            held = connection.scalar(text("SELECT pg_try_advisory_lock(:key)"), {"key": SCHEDULER_LOCK})
            identity = connection.scalar(text("SELECT pg_backend_pid()")) if held else None
            connection.commit()
            self._held, self.backend_pid = bool(held), identity
            if not held:
                self.close()
            return self._held
        except BaseException:
            self.close()
            raise

    def heartbeat(self):
        connection = self._connection
        if not self._held or connection is None or connection.closed or connection.invalidated:
            self.close()
            return False
        try:
            identity = connection.scalar(text("SELECT pg_backend_pid()"))
            connection.commit()
            if identity != self.backend_pid:
                self.close()
                return False
            return True
        except Exception:
            self.close()
            return False

    @contextmanager
    def session(self):
        if not self._held or not self.heartbeat():
            raise SchedulerLeadershipLost("Scheduler session leadership is unavailable")
        try:
            # Keep each business operation's independent commit/rollback boundary on this owning session.
            with self.database.use_session(self._connection):
                yield
        except BaseException:
            self.close()
            raise

    @contextmanager
    def transaction(self):
        if not self._held or not self.heartbeat():
            raise SchedulerLeadershipLost("Scheduler session leadership is unavailable")
        try:
            # All nested Store calls reuse this connection. Losing leadership also aborts the uncommitted tick;
            # an old process cannot continue a tick on a new pooled business connection after failover.
            with self.database.transaction(physical=self._connection) as borrowed:
                yield borrowed
        except BaseException:
            self.close()
            raise

    def close(self):
        connection, held = self._connection, self._held
        self._connection, self._held, self.backend_pid = None, False, None
        if connection is None:
            return
        try:
            if held and not connection.closed and not connection.invalidated:
                connection.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": SCHEDULER_LOCK}).close()
                connection.commit()
        except Exception:
            connection.invalidate()
        finally:
            connection.close()

    def __enter__(self):
        return self

    def __exit__(self, *_exception):
        self.close()
