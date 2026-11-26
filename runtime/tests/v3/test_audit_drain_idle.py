"""An audit drain closes early when no worker able to audit is asking for work (26/11: a leaving or rejoining member
kept every generation waiting for the full audit timeout)."""

from types import SimpleNamespace

import pytest

from heteroes import coordinator as coordinator_module
from heteroes.coordinator import Coordinator


class FakeAudits:
    def __init__(self, workers=("a", "b"), auditable=lambda elapsed: False, pending=3):
        self.available_workers, self._auditable, self.pending = set(workers), auditable, pending
        self.fatal_error, self.drain_closed, self.closed, self.elapsed = None, False, None, 0.0

    def auditable(self, window):
        assert window == coordinator_module.AUDITOR_IDLE_SECONDS
        return self._auditable(self.elapsed)

    def close_drain(self, reason):
        self.closed, self.drain_closed = reason, True


def drain(api, timeout=600.0, poll=1.0):
    clock, logged = [0.0], []

    def sleep(seconds):
        clock[0] += seconds
        api.elapsed = clock[0]

    host = SimpleNamespace(
        _audit_rate=0.05,
        _audit_timeout=timeout,
        _limit=lambda value, generation: value,
        _monotonic=lambda: clock[0],
        _sleep=sleep,
        _poll=poll,
        _check_cancel=lambda: None,
        _job=lambda *a: {},
        server=SimpleNamespace(set_generation=lambda *a: None),
        log=lambda event, **fields: logged.append((event, fields)),
    )
    Coordinator._drain_audits(host, 7, api, None)
    return clock[0], logged


def test_nobody_able_to_audit_closes_the_drain_after_the_idle_window_not_the_timeout():
    api = FakeAudits()
    waited, logged = drain(api)
    assert api.closed == "insufficient_workers"
    assert coordinator_module.AUDITOR_IDLE_SECONDS <= waited < coordinator_module.AUDITOR_IDLE_SECONDS + 2
    assert logged == [("audit_incomplete", {"generation": 7, "pending": 3, "reason": "insufficient_workers"})]


def test_an_active_auditor_keeps_the_drain_open_until_the_timeout():
    api = FakeAudits(auditable=lambda elapsed: True)
    waited, _ = drain(api, timeout=200.0)
    assert api.closed == "timeout" and 200 <= waited < 202


def test_an_auditor_that_goes_quiet_closes_the_drain_early():
    api = FakeAudits(auditable=lambda elapsed: elapsed < 90)
    waited, _ = drain(api)
    assert api.closed == "insufficient_workers" and 90 <= waited < 92


@pytest.mark.parametrize("workers", [("a",), ()])
def test_a_single_member_closes_at_once(workers):
    api = FakeAudits(workers=workers, auditable=lambda elapsed: True)
    waited, _ = drain(api)
    assert api.closed == "insufficient_workers" and waited == 0


def test_finished_audits_close_as_complete():
    api = FakeAudits(pending=0)
    drain(api)
    assert api.closed == "complete"
