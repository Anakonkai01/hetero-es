"""The managed run's scheduling (ADR-009): the chosen policy, only the selected workers, one book seeded from the ledger."""

import pytest

from heteroes.dispatch import AdmittedOnly, Greedy, GreedyTail
from heteroes.ledger import Ledger
from heteroes.product.runner import scheduling
from heteroes.worker_api import WorkerAPI
from ledger_helpers import FakeClock, batch
from test_dispatch import ask, deliver


def config(**changes):
    return {"runId": "exp", "workerIds": ["a", "b"], "schedulerPolicy": "greedy-tail", **changes}


def test_the_chosen_policy_serves_only_the_selected_workers():
    ledger = Ledger(":memory:", clock=FakeClock())
    make = scheduling(config(), ledger)
    policy = make()
    assert make.policy_name == "greedy-tail" and isinstance(policy, AdmittedOnly)
    assert policy.admitted == {"a", "b"} and isinstance(policy._inner, GreedyTail)
    assert isinstance(scheduling(config(schedulerPolicy="greedy"), ledger)()._inner, Greedy)


def test_a_restarted_run_starts_from_the_durations_in_its_ledger():
    clock = FakeClock()
    ledger = Ledger(":memory:", clock=clock)
    ledger.open_generation(batch(2))
    api = WorkerAPI(ledger, "exp", 0, lease_seconds=30.0, policy=Greedy())
    work = ask(api, "a")
    clock.advance(7.0)
    deliver(api, work)
    assert scheduling(config(), ledger)()._inner._book.estimate("a") == 7.0
    assert (
        ask(WorkerAPI(ledger, "exp", 0, lease_seconds=30.0, policy=scheduling(config(), ledger)()), "stranger") is None
    )


def test_time_limits_follow_the_measured_speeds_but_never_drop_below_the_old_fixed_ones():
    from heteroes.dispatch import SpeedBook
    from heteroes.product.runner import derived_limit

    book = SpeedBook(alpha=1.0)
    assert derived_limit(book, ["a", "b"], 8, floor=1800, factor=4) == 1800  # nothing measured yet
    book.observe("a", 20.0)
    book.observe("b", 300.0)  # a slow GPU on a long workload
    # ceil(8 / 2) = 4 candidates per worker, the slowest takes 300 s, four times that for safety
    assert derived_limit(book, ["a", "b"], 8, floor=1800, factor=4) == 4 * 4 * 300.0
    assert derived_limit(book, ["a"], 8, floor=1800, factor=4) == 1800  # a's 8 x 20 s fits in the floor
    assert derived_limit(book, ["a", "b"], 1, floor=120, factor=3) == 900.0  # one audit by the slowest member
    assert derived_limit(book, lambda: ["a"], 1, floor=120, factor=3) == 120  # members may be a function
    assert scheduling(config(), Ledger(":memory:", clock=FakeClock())).book is not None


def test_background_base_validation_is_waited_for_and_its_failure_is_raised():
    import threading

    from heteroes.product.runner import _Background

    gate, done = threading.Event(), []
    job = _Background(lambda: (gate.wait(5), done.append(True)))
    assert done == []
    gate.set()
    job.join()
    assert done == [True]

    def fail():
        raise ValueError("validation failed")

    with pytest.raises(ValueError, match="validation failed"):
        _Background(fail).join()


def test_a_coordinator_pauses_at_the_boundary_when_its_disk_is_nearly_full(tmp_path):
    # overnight 2026-10-23: a soak run failed at generation 60 with "No space left on device"; pausing keeps it resumable
    from collections import namedtuple

    from heteroes.product.runner import pause_check

    Usage = namedtuple("Usage", "total used free")
    free, said = [10 * 2**30], []
    check = pause_check(tmp_path, 4 * 2**30, said.append, usage=lambda path: Usage(0, 0, free[0]))
    assert check() is False and said == []
    free[0] = 3 * 2**30
    assert check() is True and check() is True
    assert said == [{"event": "paused_low_disk", "freeBytes": 3 * 2**30, "reserveBytes": 4 * 2**30}]
    free[0] = 10 * 2**30
    (tmp_path / "pause.flag").touch()
    assert check() is True
