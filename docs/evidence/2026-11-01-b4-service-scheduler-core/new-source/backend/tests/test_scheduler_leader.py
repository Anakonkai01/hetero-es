"""A scheduler owns one PostgreSQL session and fences every tick on that exact physical connection."""

from contextlib import contextmanager
import multiprocessing
import os
import time
import uuid

import pytest
from sqlalchemy import event, text

from backend.db.engine import Database, LAB_WRITE_LOCK
from backend.db.leadership import SchedulerLeader, SCHEDULER_LOCK


def test_distributed_scheduler_session_requires_postgresql(tmp_path):
    with Database(tmp_path / "local.sqlite") as local:
        with pytest.raises(ValueError, match="PostgreSQL"):
            SchedulerLeader(local)


def _hold_leadership(ready):
    with Database(os.environ["HETEROES_TEST_DATABASE_URL"]) as database:
        with SchedulerLeader(database) as leader:
            ready.put((leader.try_acquire(), leader.backend_pid))
            time.sleep(30)


# These real-server cases are collected only in the explicit PostgreSQL matrix, like B3's second-dialect cases.
# The SQLite profile still tests rejection of distributed mode above; it never pretends to exercise session locks.
if os.environ.get("HETEROES_TEST_DATABASE_URL"):

    @pytest.fixture
    def postgres():
        target = os.environ["HETEROES_TEST_DATABASE_URL"]
        schema = "leader_test_" + uuid.uuid4().hex
        with Database(target) as administration:
            with administration.transaction() as db:
                db.execute("CREATE SCHEMA " + schema)
            try:
                with Database(
                    target, connect_args={"options": "-csearch_path=" + schema + " -clock_timeout=2000"}
                ) as database:
                    with database.transaction() as db:
                        db.execute("CREATE TABLE tick_writes(id BIGINT PRIMARY KEY)")
                    yield database
            finally:
                with administration.transaction() as db:
                    db.execute("DROP SCHEMA " + schema + " CASCADE")

    class TestPostgreSQLSchedulerSession:
        def test_repeated_heartbeats_do_not_reacquire_or_leave_idle_transactions(self, postgres):
            queries = []
            event.listen(
                postgres.engine,
                "before_cursor_execute",
                lambda conn, cursor, statement, params, context, many: queries.append(statement),
            )
            with SchedulerLeader(postgres) as active, SchedulerLeader(postgres) as standby:
                assert SCHEDULER_LOCK != LAB_WRITE_LOCK
                assert active.try_acquire() is True
                first_acquisitions = sum("pg_try_advisory_lock" in query for query in queries)
                assert active.try_acquire() is True and active.heartbeat() is True
                assert sum("pg_try_advisory_lock" in query for query in queries) == first_acquisitions
                assert standby.try_acquire() is False
                with postgres.transaction() as db:
                    assert db.execute("SELECT 1").fetchone()[0] == 1
                    state = db.execute(
                        "SELECT state,xact_start FROM pg_stat_activity WHERE pid=:p0", (active.backend_pid,)
                    ).fetchone()
                    assert tuple(state) == ("idle", None)

        def test_graceful_release_closes_the_physical_session_and_allows_takeover(self, postgres):
            queries = []
            event.listen(
                postgres.engine,
                "before_cursor_execute",
                lambda conn, cursor, statement, params, context, many: queries.append(statement),
            )
            with SchedulerLeader(postgres) as active, SchedulerLeader(postgres) as standby:
                assert active.try_acquire()
                identity = active.backend_pid
                assert not standby.try_acquire()
                active.close()
                assert sum("pg_advisory_unlock(" in query for query in queries) == 1
                with postgres.transaction(write=False) as db:
                    assert (
                        db.execute("SELECT count(*) FROM pg_stat_activity WHERE pid=:p0", (identity,)).fetchone()[0]
                        == 0
                    )
                assert standby.try_acquire()

        def test_bound_session_never_reconnects_on_a_new_business_connection_after_loss(self, postgres):
            with SchedulerLeader(postgres) as active, SchedulerLeader(postgres) as standby:
                assert active.try_acquire()
                with pytest.raises(Exception):
                    with active.session():
                        with postgres.transaction() as db:
                            db.execute("INSERT INTO tick_writes(id) VALUES (:p0)", (1,))
                        with postgres.engine.connect() as observer:
                            assert observer.scalar(
                                text("SELECT pg_terminate_backend(:pid)"), {"pid": active.backend_pid}
                            )
                        with postgres.transaction() as db:
                            db.execute("INSERT INTO tick_writes(id) VALUES (:p0)", (2,))
                assert not active.held
                assert standby.try_acquire()
                with postgres.transaction() as db:
                    assert [row[0] for row in db.execute("SELECT id FROM tick_writes ORDER BY id")] == [1]

        def test_process_death_releases_leadership_without_a_manual_unlock(self, postgres):
            context = multiprocessing.get_context("spawn")
            ready = context.Queue()
            process = context.Process(target=_hold_leadership, args=(ready,))
            try:
                process.start()
                held, identity = ready.get(timeout=15)
                assert held and isinstance(identity, int)
                with SchedulerLeader(postgres) as standby:
                    assert not standby.try_acquire()
                    process.terminate()
                    process.join(5)
                    assert not process.is_alive()
                    deadline = time.monotonic() + 5
                    while not standby.try_acquire() and time.monotonic() < deadline:
                        time.sleep(0.05)
                    assert standby.held
            finally:
                if process.is_alive():
                    process.terminate()
                if process.pid is not None:
                    process.join(5)
                ready.close()
                ready.join_thread()

        def test_a_tick_uses_the_leader_session_and_lost_connection_cannot_commit(self, postgres):
            with SchedulerLeader(postgres) as active, SchedulerLeader(postgres) as standby:
                assert active.try_acquire()
                with active.transaction() as db:
                    assert db.execute("SELECT pg_backend_pid()").fetchone()[0] == active.backend_pid
                    db.execute("INSERT INTO tick_writes(id) VALUES (:p0)", (1,))
                    with postgres.transaction() as nested:
                        assert nested is db
                with pytest.raises(Exception):
                    with active.transaction() as db:
                        db.execute("INSERT INTO tick_writes(id) VALUES (:p0)", (2,))
                        # Kill only this test-owned scheduler session, through a separate observer connection.
                        with postgres.engine.connect() as observer:
                            assert observer.scalar(
                                text("SELECT pg_terminate_backend(:pid)"), {"pid": active.backend_pid}
                            )
                        db.execute("INSERT INTO tick_writes(id) VALUES (:p0)", (3,))
                assert not active.held
                assert standby.try_acquire()
                with postgres.transaction() as db:
                    assert [row[0] for row in db.execute("SELECT id FROM tick_writes ORDER BY id")] == [1]
