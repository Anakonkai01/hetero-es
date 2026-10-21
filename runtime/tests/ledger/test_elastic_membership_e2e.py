"""
The key invariant of ADR-009, end to end on CPU with real HTTP workers: who works on which generation does not change the
numbers. A run whose members change (a worker joins at generation 1, another leaves at generation 2, and a worker that
is never a member keeps asking) ends with exactly the weights of the hand-computed update, and every committed result
in the ledger was made by a member of its generation.
"""

import json

from heteroes.dispatch import policy_factory
from heteroes.product.membership import Membership, membership_violations
from test_coordinator_recovery import final_hash, world  # noqa: F401  (the fixture)


def test_a_run_whose_members_change_has_the_weights_of_a_run_whose_members_do_not(world, tmp_path):  # noqa: F811
    events = []
    root = tmp_path / "run"
    root.mkdir()
    holder = {}

    def started(generation):
        if generation == 1:
            requests = [{"changeId": "r1", "workerId": "w2", "action": "JOIN", "actor": "owner"}]
        elif generation == 2:
            requests = [
                {"changeId": "r1", "workerId": "w2", "action": "JOIN", "actor": "owner"},
                {"changeId": "r2", "workerId": "w1", "action": "LEAVE", "actor": "owner"},
            ]
        else:
            requests = []
        (root / "membership-requests.json").write_text(json.dumps({"requests": requests}))
        holder["membership"].apply(generation, holder["coordinator"])

    coordinator = world.coordinator(generation_started=started, policy_factory=lambda: holder["policy"]())
    membership = Membership(coordinator.ledger, "exp", ["w1"], root, events.append)
    holder.update(
        coordinator=coordinator, membership=membership, policy=policy_factory("greedy-tail", membership.current)
    )
    halt, steps = world.workers(coordinator, names=("w1", "w2", "stranger"))
    try:
        coordinator.run(4)
    finally:
        halt()
    assert final_hash(coordinator) == world.oracle(4)
    ledger = coordinator.ledger
    assert [ledger.members_at("exp", g) for g in range(4)] == [{"w1"}, {"w1", "w2"}, {"w2"}, {"w2"}]
    assert membership_violations(ledger, "exp") == []
    # w1 alone did generation 0 and w2 alone generations 2 and 3; the stranger never got a candidate
    assert {worker for _, _, worker in ledger.list_committed_attempts("exp")} == {"w1", "w2"}


def test_a_result_from_a_worker_that_was_not_a_member_is_found(world):  # noqa: F811
    coordinator = world.coordinator()
    halt, _ = world.workers(coordinator, names=("w1",))
    try:
        coordinator.run(1)
    finally:
        halt()
    ledger = coordinator.ledger
    ledger.record_membership("exp", "initial:other", "other", "JOIN", 0, "experiment")
    violations = membership_violations(ledger, "exp")
    assert violations and all(v["workerId"] == "w1" and v["generation"] == 0 for v in violations)
