"""
ADR-009 in the ledger: who may work for an experiment from which generation on (elastic membership), and leases that ran out
written down when they are taken over. Both are additive tables, like `generation_context`: a candidate6 ledger still opens.
"""

import sqlite3

import pytest

from heteroes.ledger import Ledger, LedgerError
from ledger_helpers import FakeClock, batch, fail, lease, submit


def fresh(clock=None):
    ledger = Ledger(":memory:", clock=clock or FakeClock())
    ledger.open_generation(batch(3))
    return ledger


# ---- a lease that runs out


def test_a_lease_that_ran_out_is_written_down_when_another_worker_takes_the_candidate():
    clock = FakeClock()
    ledger = fresh(clock)
    first = lease(ledger, 0, "slow", 30.0)
    clock.advance(31.0)
    second = lease(ledger, 0, "fast", 30.0)
    assert ledger.list_expired("exp") == [("exp/g0/c0", 1, "slow", first.deadline)]
    submit(ledger, second)
    assert ledger.list_expired("exp") == [("exp/g0/c0", 1, "slow", first.deadline)]


def test_a_reported_failure_and_a_late_delivery_are_not_expiries():
    clock = FakeClock()
    ledger = fresh(clock)
    failed = lease(ledger, 0, "a", 30.0)
    fail(ledger, failed)
    lease(ledger, 0, "b", 30.0)  # after a failure report: the attempt ended, it did not run out
    late = lease(ledger, 1, "a", 30.0)
    clock.advance(40.0)
    submit(ledger, late)  # late but nobody took it in between: a result, not an expiry
    assert ledger.list_expired("exp") == []


# ---- membership


def test_members_change_from_a_generation_on():
    ledger = fresh()
    assert ledger.record_membership("exp", "start-a", "a", "JOIN", 0, "experiment")
    assert ledger.record_membership("exp", "start-b", "b", "JOIN", 0, "experiment")
    assert ledger.record_membership("exp", "r1", "late", "JOIN", 10, "owner")
    assert ledger.record_membership("exp", "r2", "b", "LEAVE", 30, "system")
    assert ledger.members_at("exp", 0) == {"a", "b"}
    assert ledger.members_at("exp", 9) == {"a", "b"}
    assert ledger.members_at("exp", 10) == {"a", "b", "late"}
    assert ledger.members_at("exp", 30) == {"a", "late"}
    assert ledger.members_at("other", 30) == set()
    changes = ledger.list_membership("exp")
    assert [(c.change_id, c.worker_id, c.action, c.effective_generation, c.actor) for c in changes] == [
        ("start-a", "a", "JOIN", 0, "experiment"),
        ("start-b", "b", "JOIN", 0, "experiment"),
        ("r1", "late", "JOIN", 10, "owner"),
        ("r2", "b", "LEAVE", 30, "system"),
    ]


def test_the_same_change_twice_is_written_once_and_a_different_one_with_its_id_is_refused():
    ledger = fresh()
    assert ledger.record_membership("exp", "r1", "late", "JOIN", 10, "owner") is True
    assert ledger.record_membership("exp", "r1", "late", "JOIN", 10, "owner") is False  # a restarted runner repeats it
    with pytest.raises(LedgerError, match="r1"):
        ledger.record_membership("exp", "r1", "late", "JOIN", 11, "owner")
    assert len(ledger.list_membership("exp")) == 1


@pytest.mark.parametrize(
    "args",
    [
        ("", "w", "JOIN", 0, "owner"),
        ("r", "", "JOIN", 0, "owner"),
        ("r", "w", "ADD", 0, "owner"),
        ("r", "w", "JOIN", -1, "owner"),
        ("r", "w", "JOIN", True, "owner"),
        ("r", "w", "JOIN", 0, ""),
        ("r", 3, "JOIN", 0, "owner"),
    ],
)
def test_malformed_membership_changes_are_refused(args):
    with pytest.raises((LedgerError, TypeError, ValueError)):
        fresh().record_membership("exp", *args)


def test_a_ledger_written_before_these_tables_existed_still_opens(tmp_path):
    path = tmp_path / "ledger.sqlite"
    Ledger(path, clock=FakeClock()).close()
    with sqlite3.connect(path) as db:  # a candidate6 file: schema 6 without the two new tables
        db.execute("DROP TABLE membership")
        db.execute("DROP TABLE expiry")
    ledger = Ledger(path, clock=FakeClock())
    assert ledger.list_membership("exp") == [] and ledger.list_expired("exp") == []
    ledger.close()
