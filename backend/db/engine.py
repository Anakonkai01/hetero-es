"""SQLAlchemy Core connection/transaction ownership for SQLite and PostgreSQL."""

from contextlib import contextmanager, nullcontext
from pathlib import Path
import re
import threading

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.pool import NullPool

from .bindings import bind_parameters
from .rows import Result

# Root transaction lock; scheduler session leadership must use a different key.
LAB_WRITE_LOCK = 0x48455445524F4553
_MUTATION = re.compile(r"^\s*(INSERT|UPDATE|DELETE|CREATE|ALTER|DROP|TRUNCATE|REPLACE)\b", re.IGNORECASE)
_DML = re.compile(r"^\s*(INSERT|UPDATE|DELETE)\b", re.IGNORECASE)


class Connection:
    """One borrowed transaction connection, with the repository's row/binding protocol."""

    def __init__(self, connection, dialect, write, schema_ready=False):
        self._connection, self.dialect, self.write = connection, dialect, write
        self.closed, self.rollback_only = False, False
        self.schema_ready = schema_ready

    def _check(self, statement):
        if self.closed:
            raise RuntimeError("Database transaction connection is closed")
        if not self.write and _MUTATION.match(statement):
            raise RuntimeError("Database transaction is read only")

    def execute(self, statement, parameters=()):
        self._check(statement)
        sql, bindings = bind_parameters(statement, parameters)
        # PostgreSQL otherwise keeps the whole transaction aborted after a caught integrity failure. The lab's
        # serialization lock was acquired on the root transaction, outside this statement savepoint.
        savepoint = (
            self._connection.begin_nested() if self.dialect == "postgresql" and _DML.match(sql) else nullcontext()
        )
        with savepoint:
            result = self._connection.execute(text(sql), bindings)
        return Result(result)

    def executemany(self, statement, parameter_sets):
        self._check(statement)
        compiled = [bind_parameters(statement, values) for values in parameter_sets]
        if not compiled:
            raise ValueError("An executemany call needs at least one parameter set")
        sql = compiled[0][0]
        savepoint = (
            self._connection.begin_nested() if self.dialect == "postgresql" and _DML.match(sql) else nullcontext()
        )
        with savepoint:
            result = self._connection.execute(text(sql), [bindings for _, bindings in compiled])
        return Result(result)

    def begin_write(self):
        if self.closed:
            raise RuntimeError("Database transaction connection is closed")
        if not self.write:
            raise RuntimeError("Cannot upgrade an active read transaction")
        # Ownership is established before yielding the outer transaction, not by a nested BEGIN.
        return None


class Database:
    def __init__(self, target, *, lock=None, connect_args=None):
        if isinstance(target, URL):
            url = target
        elif "://" in str(target):
            url = make_url(str(target))
        else:
            path = Path(target).resolve()
            path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            url = URL.create("sqlite+pysqlite", database=str(path))
        if url.drivername in {"postgres", "postgresql"}:
            url = url.set(drivername="postgresql+psycopg")
        if url.drivername not in {"sqlite", "sqlite+pysqlite", "postgresql+psycopg"}:
            raise ValueError("Only SQLite and PostgreSQL with psycopg 3 are supported")
        self.lock = lock if lock is not None else threading.RLock()
        self.schema_ready = False
        self._local = threading.local()
        options = {"hide_parameters": True, "pool_pre_ping": True}
        arguments = dict(connect_args or {})
        if url.get_backend_name() == "sqlite":
            arguments.update(timeout=20, check_same_thread=False)
            options["poolclass"] = NullPool
        self.engine = create_engine(url, connect_args=arguments, **options)
        self.url, self.dialect = self.engine.url, self.engine.dialect.name
        if self.dialect == "sqlite":

            @event.listens_for(self.engine, "connect")
            def sqlite_connection(connection, _record):
                connection.isolation_level = None

            @event.listens_for(self.engine, "begin")
            def sqlite_begin(connection):
                connection.exec_driver_sql(
                    "BEGIN IMMEDIATE" if connection.info.get("heteroes_write", True) else "BEGIN"
                )

    @contextmanager
    def transaction(self, *, write=None, physical=None):
        with self.lock:
            existing = getattr(self._local, "connection", None)
            if existing is not None:
                if physical is not None and physical is not existing._connection:
                    raise RuntimeError("Cannot replace the active transaction connection")
                if write is True and not existing.write:
                    raise RuntimeError("Cannot upgrade an active read transaction")
                try:
                    yield existing
                except BaseException:
                    existing.rollback_only = True
                    raise
                return
            writable = True if write is None else write
            if physical is None:
                physical = getattr(self._local, "session", None)
            if physical is None:
                owner = self.engine.connect()
            else:
                if physical.engine is not self.engine or physical.closed or physical.invalidated:
                    raise RuntimeError("Dedicated transaction connection is unavailable")
                owner = nullcontext(physical)
            with owner as physical:
                connection_info = physical.info
                connection_info["heteroes_write"] = writable
                transaction = physical.begin()
                borrowed = Connection(physical, self.dialect, writable, self.schema_ready)
                try:
                    if self.dialect == "postgresql" and writable:
                        physical.execute(
                            text("SELECT pg_advisory_xact_lock(:lab_write_lock)"), {"lab_write_lock": LAB_WRITE_LOCK}
                        ).close()
                    self._local.connection = borrowed
                    try:
                        yield borrowed
                    except BaseException:
                        transaction.rollback()
                        raise
                    else:
                        if borrowed.rollback_only:
                            transaction.rollback()
                            raise RuntimeError("Database transaction must rollback after a nested scope failed")
                        transaction.commit()
                finally:
                    borrowed.closed = True
                    self._local.connection = None
                    connection_info.pop("heteroes_write", None)

    def close(self):
        self.engine.dispose()

    @contextmanager
    def use_session(self, physical):
        """Bind subsequent root transactions to a caller-owned session without merging their commit boundaries."""
        with self.lock:
            if getattr(self._local, "connection", None) is not None:
                raise RuntimeError("Cannot bind a physical session inside an active transaction")
            previous = getattr(self._local, "session", None)
            if previous is not None and previous is not physical:
                raise RuntimeError("Cannot replace the active database session")
            if physical.engine is not self.engine or physical.closed or physical.invalidated:
                raise RuntimeError("Dedicated database session is unavailable")
            self._local.session = physical
            try:
                yield
            finally:
                self._local.session = previous

    def ping(self):
        with self.transaction(write=False) as connection:
            return connection.execute("SELECT 1").fetchone()[0] == 1

    def initialize(self, passwords, hasher):
        from .schema import initialize_database

        initialize_database(self, passwords, hasher)

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        self.close()
