"""Business telemetry belongs only to a live scheduler leader, with actual PostgreSQL session fencing."""

from contextlib import ExitStack
import os

from fastapi.testclient import TestClient
import pytest

from backend.apps.factory import create_app
from backend.db.leadership import SchedulerLeader
from backend.services.devices import AgentRuntime
from test_observability import samples


def test_scheduler_role_suppresses_business_series_when_standby_and_exposes_them_when_active(tmp_path):
    app = create_app(tmp_path / "role.sqlite", {}, AgentRuntime(), dispatch=False, service="scheduler")
    with ExitStack() as cleanup:
        client = cleanup.enter_context(TestClient(app))
        controller = app.state.scheduler
        text = client.get("/metrics").text
        assert not samples(text, "heteroes_runs")
        assert samples(text, "heteroes_scheduler_leader")[0].value == 0
        if app.state.store.database.dialect == "postgresql":
            leader = cleanup.enter_context(SchedulerLeader(app.state.store.database))
            assert leader.try_acquire()
            controller._leader = leader
        controller.active = True
        text = client.get("/metrics").text
        assert samples(text, "heteroes_scheduler_leader")[0].value == 1
        assert samples(text, "heteroes_runs") and samples(text, "heteroes_queue_depth")[0].value == 0
        controller.active = False
        assert not samples(client.get("/metrics").text, "heteroes_runs")


if os.environ.get("HETEROES_TEST_DATABASE_URL"):

    def test_metrics_reads_use_the_owning_session_and_stop_on_connection_loss(tmp_path):
        app = create_app(tmp_path / "fenced.sqlite", {}, AgentRuntime(), dispatch=False, service="scheduler")
        store, controller = app.state.store, app.state.scheduler
        with TestClient(app) as client, SchedulerLeader(store.database) as leader:
            assert leader.try_acquire()
            controller._leader = leader
            controller.active = True

            def identity():
                with store.database.transaction(write=False) as db:
                    return db.execute("SELECT pg_backend_pid()").fetchone()[0]

            assert controller.read_metrics(identity) == leader.backend_pid
            assert samples(client.get("/metrics").text, "heteroes_scheduler_leader")[0].value == 1
            leader._connection.invalidate()
            assert not samples(client.get("/metrics").text, "heteroes_runs")
            assert controller.read_metrics(identity) is None and controller.active is False

    def test_a_standby_cannot_export_business_data_even_with_a_stale_active_flag(tmp_path):
        app = create_app(tmp_path / "standby.sqlite", {}, AgentRuntime(), dispatch=False, service="scheduler")
        store, controller = app.state.store, app.state.scheduler
        with (
            TestClient(app) as client,
            SchedulerLeader(store.database) as owner,
            SchedulerLeader(store.database) as standby,
        ):
            assert owner.try_acquire() and not standby.try_acquire()
            controller._leader = standby
            controller.active = True
            text = client.get("/metrics").text
            assert samples(text, "heteroes_scheduler_leader")[0].value == 0
            assert not samples(text, "heteroes_runs") and controller.active is False


if os.environ.get("HETEROES_TEST_DATABASE_URL"):

    def test_graceful_scheduler_stop_waits_for_an_owned_metrics_read_before_closing_session(tmp_path):
        import threading
        from backend.services.store import Store
        from backend.services.scheduler_controller import SchedulerController

        store = Store(tmp_path / "stop.sqlite", {}, AgentRuntime())
        controller = SchedulerController(store, interval=0.01)
        stop, dispatched, reading, release = [threading.Event() for _ in range(4)]
        store._dispatch_once = dispatched.set
        scheduler = threading.Thread(target=controller.run, args=(stop,))
        results = []

        def read():
            reading.set()
            assert release.wait(5)
            with store.database.transaction(write=False) as db:
                return db.execute("SELECT pg_backend_pid()").fetchone()[0]

        reader = threading.Thread(target=lambda: results.append(controller.read_metrics(read)))
        try:
            scheduler.start()
            assert dispatched.wait(5)
            identity = controller.backend_pid
            reader.start()
            assert reading.wait(5)
            stop.set()
            scheduler.join(0.15)
            assert scheduler.is_alive(), "Graceful shutdown must retain the owning session until its read completes"
            release.set()
            reader.join(5)
            scheduler.join(5)
            assert not reader.is_alive() and not scheduler.is_alive() and results == [identity]
        finally:
            release.set()
            stop.set()
            if reader.ident is not None:
                reader.join(5)
            scheduler.join(5)
            store.close()
