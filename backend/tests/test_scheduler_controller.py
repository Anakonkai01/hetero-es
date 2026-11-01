"""Only the active scheduler may dispatch; a graceful stop lets the waiting controller take over."""

import os
import threading
from types import SimpleNamespace

from backend.services.scheduler_controller import SchedulerController
from backend.services.devices import AgentRuntime
from backend.services.store import Store


def test_local_controller_preserves_the_existing_dispatch_stop_contract():
    calls, stop = [], threading.Event()
    local = SimpleNamespace(database=SimpleNamespace(dialect="sqlite"), dispatch=lambda signal: calls.append(signal))
    controller = SchedulerController(local)
    controller.run(stop)
    assert calls == [stop] and controller.active is False


if os.environ.get("HETEROES_TEST_DATABASE_URL"):

    def test_postgres_standby_never_dispatches_until_the_active_controller_releases(tmp_path):
        path = tmp_path / "controllers.sqlite"
        first, second = Store(path, {}, AgentRuntime()), Store(path, {}, AgentRuntime())
        controllers = [SchedulerController(first, interval=0.01), SchedulerController(second, interval=0.01)]
        stops, ticks = [threading.Event(), threading.Event()], [threading.Event(), threading.Event()]
        events, errors = [], []

        def dispatch(number, store):
            with store.db() as db:
                identity = db.execute("SELECT pg_backend_pid()").fetchone()[0]
                if identity != controllers[number].backend_pid:
                    errors.append("Dispatch used a pooled session instead of the owning scheduler")
                db.execute(
                    "INSERT INTO settings(key,value) VALUES (:p0,:p1) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                    ("controller-owner", str(number)),
                )
            events.append(number)
            ticks[number].set()

        first._dispatch_once = lambda: dispatch(0, first)
        second._dispatch_once = lambda: dispatch(1, second)
        threads = [
            threading.Thread(target=controller.run, args=(stop,)) for controller, stop in zip(controllers, stops)
        ]
        try:
            threads[0].start()
            assert ticks[0].wait(5)
            threads[1].start()
            assert not ticks[1].wait(0.2)
            assert controllers[0].active and not controllers[1].active and set(events) == {0}
            stops[0].set()
            threads[0].join(5)
            assert not threads[0].is_alive()
            assert ticks[1].wait(5)
            assert controllers[1].active and not controllers[0].active
            assert not errors
            stops[1].set()
            threads[1].join(5)
            with first.db() as db:
                assert (
                    db.execute("SELECT value FROM settings WHERE key=:p0", ("controller-owner",)).fetchone()[0] == "1"
                )
        finally:
            for stop in stops:
                stop.set()
            for thread in threads:
                if thread.ident is not None:
                    thread.join(5)
            first.close()
            second.close()


if os.environ.get("HETEROES_TEST_DATABASE_URL"):

    def test_fenced_ticks_keep_independent_job_transactions_and_other_jobs_progress(tmp_path):
        store = Store(tmp_path / "job-boundaries.sqlite", {}, AgentRuntime())
        stop, finished = threading.Event(), threading.Event()
        controller = SchedulerController(store, interval=0.01)

        def dispatch():
            try:
                with store.db() as db:
                    db.execute("INSERT INTO settings(key,value) VALUES (:p0,:p1)", ("committed-before-failure", "true"))
                try:
                    with store.db() as db:
                        db.execute("INSERT INTO settings(key,value) VALUES (:p0,:p1)", ("failed-job", "true"))
                        raise ValueError("fixture job failure")
                except ValueError:
                    pass
                with store.db() as db:
                    db.execute("INSERT INTO settings(key,value) VALUES (:p0,:p1)", ("another-job-progress", "true"))
            finally:
                stop.set()
                finished.set()

        store._dispatch_once = dispatch
        thread = threading.Thread(target=controller.run, args=(stop,))
        try:
            thread.start()
            assert finished.wait(5)
            thread.join(5)
            assert not thread.is_alive()
            with store.db() as db:
                assert (
                    db.execute("SELECT value FROM settings WHERE key=:p0", ("committed-before-failure",)).fetchone()[0]
                    == "true"
                )
                assert (
                    db.execute("SELECT value FROM settings WHERE key=:p0", ("another-job-progress",)).fetchone()[0]
                    == "true"
                )
                assert db.execute("SELECT count(*) FROM settings WHERE key=:p0", ("failed-job",)).fetchone()[0] == 0
        finally:
            stop.set()
            thread.join(5)
            store.close()
