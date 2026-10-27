"""
D10 (ADR-012): one automatic recovery per worker and run after a restore mismatch.

A restore mismatch quarantines the worker in the ledger (frozen contract: a quarantine is never lifted). The recovered
worker therefore comes back under a new identity, `<worker>~r1`, so the ledger, its audits and every earlier result keep
their meaning. Both sides keep a persisted record, so a restart of either never gives a second recovery:

- worker (`WorkerBudget`): spent before the recovery starts. Recovery = stop, keep the fault report in the outbox until
  ACKed, reload the base weights from the verified model files, download and verify the canonical parent, check that a
  perturbation restores exactly, then ask for work as the alias;
- coordinator (`CoordinatorRecoveries`): the alias is admitted only for a worker quarantined for a restore mismatch,
  once, and gets work only from the generation after the fault (a boundary). A second restore fault quarantines the
  alias for good: an operator has to look at it. Device approval and contribution states are never changed.
"""

import json
from pathlib import Path

ALIAS_SUFFIX = "~r1"


def alias(worker_id):
    if worker_id.endswith(ALIAS_SUFFIX):
        raise ValueError("a recovered worker gets no second recovery")
    return worker_id + ALIAS_SUFFIX


def base_of(worker_id):
    """The original identity of a recovered worker, or None for an ordinary one."""
    return worker_id[: -len(ALIAS_SUFFIX)] if worker_id.endswith(ALIAS_SUFFIX) else None


def _write(path, value):
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, sort_keys=True) + "\n")
    temporary.replace(path)


class WorkerBudget:
    """The worker's one recovery per run (`run_key`: the recipe hash), persisted beside its outbox."""

    def __init__(self, path, run_key):
        self.path, self.run_key = Path(path), run_key

    def _state(self):
        return json.loads(self.path.read_text()) if self.path.exists() else {}

    def spent(self):
        return self._state().get(self.run_key) is not None

    def spend(self, worker_id):
        state = self._state()
        if state.get(self.run_key) is not None:
            raise RuntimeError("the restore recovery of this run was already used")
        state[self.run_key] = {"worker": worker_id, "alias": alias(worker_id), "completed": False}
        _write(self.path, state)
        return state[self.run_key]["alias"]

    def complete(self):
        state = self._state()
        state[self.run_key]["completed"] = True
        _write(self.path, state)

    def done(self):
        entry = self._state().get(self.run_key)
        return entry is not None and entry["completed"]

    def fail(self, reason):
        state = self._state()
        state[self.run_key]["failed"] = reason
        _write(self.path, state)

    def failed(self):
        entry = self._state().get(self.run_key)
        return entry is not None and entry.get("failed") is not None

    def alias(self):
        entry = self._state().get(self.run_key)
        return None if entry is None else entry["alias"]


class CoordinatorRecoveries:
    """Which quarantined workers came back under their alias, and from which generation they may work."""

    def __init__(self, path):
        self.path = Path(path)

    def _state(self):
        return json.loads(self.path.read_text()) if self.path.exists() else {}

    def admit(self, alias_id, quarantine, generation_of):
        """The grant {alias, faultGeneration} of `alias_id`, recorded on its first request, or None if it is not the
        alias of a worker quarantined for a restore mismatch. `generation_of(candidate_id)` dates the fault."""
        base = base_of(alias_id)
        if base is None:
            return None
        state = self._state()
        if base not in state:
            faults = [q for q in quarantine if q.worker_id == base and q.reason == "RESTORE_MISMATCH"]
            if not faults:
                return None
            state[base] = {"alias": alias_id, "faultGeneration": max(generation_of(q.candidate_id) for q in faults)}
            _write(self.path, state)
        return state[base]

    def granted(self, base):
        return base in self._state()
