"""
Elastic membership on the coordinator (ADR-009).

The device agent appends the lab's requests to `membership-requests.json` in the run directory (a worker joins with its
compute credential, or leaves). At the start of each generation the runner calls `apply`: every request not seen before is
checked, written to the ledger as effective from that generation, and the coordinator is told the new members and
credentials. A generation that is already open in the ledger (a restarted coordinator resumes it) keeps its members;
the change then waits for the next boundary, so nobody leaves a generation it has already committed work to.

`membership.json` is what the supervisor and the lab read: the members now, the workers that left, the refused requests.
The credentials of workers that joined are kept apart in `membership-grants.json` (private, like `device-grants.json`).
Nothing here changes what a candidate computes: membership only decides which worker may evaluate which candidate.
"""

from .files import read_json, write_json


class Membership:
    def __init__(self, ledger, experiment_id, initial, root, emit, grants=None):
        self.ledger, self.experiment_id, self.root, self.emit = ledger, experiment_id, root, emit
        self.initial = list(initial)
        self.grants = None if grants is None else dict(grants)  # worker -> credential; None: a shared-token coordinator
        self.generation = 0
        state = read_json(root / "membership.json", {})
        self.refused = {item["changeId"] for item in state.get("refused", []) if isinstance(item, dict)}
        self._refused_items = [item for item in state.get("refused", []) if isinstance(item, dict)]
        if self.grants is not None:
            self.grants.update(read_json(root / "membership-grants.json", {}))  # workers that joined before a restart

    def all_grants(self) -> dict[str, str] | None:
        return None if self.grants is None else dict(self.grants)

    def current(self) -> list[str]:
        return sorted(self.ledger.members_at(self.experiment_id, self.generation))

    def apply(self, generation, coordinator) -> None:
        if not self.ledger.list_membership(self.experiment_id):
            for worker in self.initial:
                self.ledger.record_membership(self.experiment_id, f"initial:{worker}", worker, "JOIN", 0, "experiment")
        opened = any(g.generation == generation for g in self.ledger.list_generations(self.experiment_id))
        known = {change.change_id for change in self.ledger.list_membership(self.experiment_id)}
        if not opened:
            for item in read_json(self.root / "membership-requests.json", {}).get("requests", []):
                change = item.get("changeId") if isinstance(item, dict) else None
                if change in known or change in self.refused:
                    continue
                reason = self._check(item, generation)
                if reason:
                    self._refuse(item, reason, generation)
                    continue
                self.ledger.record_membership(
                    self.experiment_id, change, item["workerId"], item["action"], generation, item["actor"]
                )
                known.add(change)
                if item["action"] == "JOIN" and self.grants is not None:
                    self.grants[item["workerId"]] = item["grant"]
                    joined = read_json(self.root / "membership-grants.json", {})
                    write_json(self.root / "membership-grants.json", {**joined, item["workerId"]: item["grant"]})
                self.emit(
                    {
                        "event": "membership_changed",
                        "generation": generation,
                        "workerId": item["workerId"],
                        "action": item["action"],
                        "actor": item["actor"],
                        "changeId": change,
                    }
                )
        self.generation = generation
        members = self.current()
        tokens = None if self.grants is None else {w: self.grants[w] for w in members if w in self.grants}
        coordinator.set_members(members, tokens)
        everyone = {change.worker_id for change in self.ledger.list_membership(self.experiment_id)}
        write_json(
            self.root / "membership.json",
            {
                "generation": generation,
                "members": members,
                "left": sorted(everyone - set(members)),
                "refused": self._refused_items,
            },
        )

    def _check(self, item, generation) -> str | None:
        if not isinstance(item, dict) or not isinstance(item.get("changeId"), str) or not item["changeId"]:
            return "a change needs an id"
        if not isinstance(item.get("workerId"), str) or not item["workerId"]:
            return "a change needs a worker"
        if not isinstance(item.get("actor"), str) or not item["actor"]:
            return "a change needs an actor"
        if item.get("action") not in ("JOIN", "LEAVE"):
            return "the action is JOIN or LEAVE"
        members = self.ledger.members_at(self.experiment_id, generation)
        worker = item["workerId"]
        if item["action"] == "JOIN":
            if worker in members:
                return "already a member"
            if self.grants is not None:
                grant = item.get("grant")
                if not isinstance(grant, str) or not grant or grant in self.grants.values():
                    return "a joining worker needs its own credential"
        else:
            if worker not in members:
                return "not a member"
            if members == {worker}:
                return "the last member cannot leave"
        return None

    def _refuse(self, item, reason, generation) -> None:
        change = item.get("changeId") if isinstance(item, dict) else None
        self.refused.add(change)
        self._refused_items.append({"changeId": change, "reason": reason, "generation": generation})
        self.emit({"event": "membership_refused", "generation": generation, "changeId": change, "reason": reason})


def membership_violations(ledger, experiment_id):
    """Committed results made by a worker that was not a member of that generation (empty for a run that never recorded
    membership). A verifier of an elastic run requires this to be empty (ADR-009)."""
    if not ledger.list_membership(experiment_id):
        return []
    members = {}
    found = []
    for generation, candidate_id, worker_id in ledger.list_committed_attempts(experiment_id):
        if generation not in members:
            members[generation] = ledger.members_at(experiment_id, generation)
        if worker_id not in members[generation]:
            found.append({"generation": generation, "candidateId": candidate_id, "workerId": worker_id})
    return found
