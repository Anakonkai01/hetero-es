"""
Elastic membership on the coordinator (ADR-009): requests written by the device agent are applied at a generation boundary,
recorded in the ledger once, and change who may lease, audit and authenticate; a refused request is reported, never applied.
"""

import json

import pytest

from heteroes.http_transport import CoordinatorServer
from heteroes.ledger import Ledger
from heteroes.product.membership import Membership
from ledger_helpers import FakeClock, batch


class FakeCoordinator:
    def __init__(self):
        self.calls = []

    def set_members(self, members, device_tokens=None):
        self.calls.append((members, device_tokens))


def request(root, *items):
    path = root / "membership-requests.json"
    old = json.loads(path.read_text())["requests"] if path.exists() else []
    path.write_text(json.dumps({"requests": old + list(items)}))


def join(change, worker, grant="g-" + "x", actor="owner"):
    return {"changeId": change, "workerId": worker, "action": "JOIN", "actor": actor, "grant": grant}


def leave(change, worker, actor="owner"):
    return {"changeId": change, "workerId": worker, "action": "LEAVE", "actor": actor}


@pytest.fixture
def world(tmp_path):
    ledger = Ledger(":memory:", clock=FakeClock())
    coordinator = FakeCoordinator()
    events = []
    membership = Membership(ledger, "exp", ["a", "b"], tmp_path, events.append, grants={"a": "ga", "b": "gb"})
    return ledger, coordinator, membership, events, tmp_path


def test_the_starting_members_are_recorded_once_from_generation_0(world):
    ledger, coordinator, membership, events, root = world
    membership.apply(0, coordinator)
    membership.apply(0, coordinator)  # a restarted runner
    assert [(c.change_id, c.worker_id, c.effective_generation) for c in ledger.list_membership("exp")] == [
        ("initial:a", "a", 0),
        ("initial:b", "b", 0),
    ]
    assert membership.current() == ["a", "b"]
    assert coordinator.calls[-1] == (["a", "b"], {"a": "ga", "b": "gb"})
    assert json.loads((root / "membership.json").read_text())["members"] == ["a", "b"]


def test_a_join_and_a_leave_take_effect_at_the_next_boundary_and_change_the_credentials(world):
    ledger, coordinator, membership, events, root = world
    membership.apply(0, coordinator)
    request(root, join("r1", "late", grant="glate"))
    membership.apply(10, coordinator)
    assert membership.current() == ["a", "b", "late"]
    assert coordinator.calls[-1] == (["a", "b", "late"], {"a": "ga", "b": "gb", "late": "glate"})
    request(root, leave("r2", "b"))
    membership.apply(30, coordinator)
    assert membership.current() == ["a", "late"]
    assert coordinator.calls[-1] == (["a", "late"], {"a": "ga", "late": "glate"})
    assert ledger.members_at("exp", 29) == {"a", "b", "late"} and ledger.members_at("exp", 30) == {"a", "late"}
    changed = [e for e in events if e["event"] == "membership_changed"]
    assert [(e["workerId"], e["action"], e["generation"]) for e in changed] == [
        ("late", "JOIN", 10),
        ("b", "LEAVE", 30),
    ]
    state = json.loads((root / "membership.json").read_text())
    assert state["members"] == ["a", "late"] and state["left"] == ["b"] and state["generation"] == 30
    assert "glate" not in (root / "membership.json").read_text()  # the lab reads this file: no credential in it
    restarted = Membership(ledger, "exp", ["a", "b"], root, events.append, grants={"a": "ga", "b": "gb"})
    restarted.apply(31, coordinator)  # a restarted runner still knows the joined worker's credential
    assert coordinator.calls[-1] == (["a", "late"], {"a": "ga", "late": "glate"})


@pytest.mark.parametrize(
    "bad,reason",
    [
        (join("r1", "a"), "already a member"),
        (leave("r1", "nobody"), "not a member"),
        (join("r1", "late", grant=""), "credential"),
        (join("r1", "late", grant="ga"), "credential"),
        ({"changeId": "r1", "workerId": "late", "action": "ADD", "actor": "owner"}, "action"),
        ({"changeId": "", "workerId": "late", "action": "JOIN", "actor": "owner", "grant": "g"}, "change"),
    ],
)
def test_a_wrong_request_is_refused_and_reported_not_applied(world, bad, reason):
    ledger, coordinator, membership, events, root = world
    membership.apply(0, coordinator)
    request(root, bad)
    membership.apply(1, coordinator)
    assert membership.current() == ["a", "b"] and len(ledger.list_membership("exp")) == 2
    refused = [e for e in events if e["event"] == "membership_refused"]
    assert len(refused) == 1 and reason in refused[0]["reason"]
    membership.apply(2, coordinator)  # reported once, not again at every boundary
    assert len([e for e in events if e["event"] == "membership_refused"]) == 1


def test_the_last_member_cannot_leave(world):
    ledger, coordinator, membership, events, root = world
    membership.apply(0, coordinator)
    request(root, leave("r1", "a"), leave("r2", "b"))
    membership.apply(1, coordinator)
    assert membership.current() == ["b"]
    assert [e["reason"] for e in events if e["event"] == "membership_refused"] == ["the last member cannot leave"]


def test_a_generation_already_open_keeps_its_members_and_the_change_waits(world):
    # a coordinator restarted inside generation 5 resumes it: a worker that committed there must stay a member of it
    ledger, coordinator, membership, events, root = world
    membership.apply(0, coordinator)
    ledger.open_generation(batch(2, generation=5))
    request(root, leave("r1", "b"))
    membership.apply(5, coordinator)
    assert membership.current() == ["a", "b"] and ledger.members_at("exp", 5) == {"a", "b"}
    membership.apply(6, coordinator)
    assert membership.current() == ["a"] and ledger.members_at("exp", 6) == {"a"}


def test_without_device_credentials_only_the_members_change(tmp_path):
    ledger = Ledger(":memory:", clock=FakeClock())
    coordinator = FakeCoordinator()
    membership = Membership(ledger, "exp", ["a"], tmp_path, lambda e: None, grants=None)
    membership.apply(0, coordinator)
    request(tmp_path, {"changeId": "r1", "workerId": "late", "action": "JOIN", "actor": "owner"})
    membership.apply(1, coordinator)
    assert coordinator.calls[-1] == (["a", "late"], None)


def test_the_server_swaps_credentials_whole_and_checks_them():
    server = CoordinatorServer(None, device_tokens={"a": "ga"})
    server.set_device_tokens({"a": "ga", "late": "glate"})
    assert server.device_tokens == {"a": "ga", "late": "glate"}
    for bad in ({}, {"a": ""}, {"a": "same", "b": "same"}):
        with pytest.raises(ValueError):
            server.set_device_tokens(bad)
    assert server.device_tokens == {"a": "ga", "late": "glate"}
    with pytest.raises(ValueError):
        CoordinatorServer(None, token="t").set_device_tokens(
            {"a": "ga"}
        )  # a shared-token server has no per-device ones
