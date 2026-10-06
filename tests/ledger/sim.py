"""
Fake workers on simulated time (SimPy). The clock of the ledger IS the clock of the simulation, so a slow worker whose
lease runs out, a worker that disappears, a lost acknowledgement: all of it happens by itself, with no sleeping.
Rewards come from `oracle_reward`, so the right answer of a generation is known in advance.

Nothing here is the ledger: the ledger is only called, like the coordinator will call it. What the workers did is in
`cluster.log`: (time, worker, event, candidate index, detail).
"""
from dataclasses import dataclass

import simpy

from harness import LEASE_SECONDS, oracle_reward
from heteroes.ledger import (
    CandidateState,
    FailureKind,
    GenerationState,
    Ledger,
    LedgerError,
    SubmitOutcome,
    WorkerQuarantinedError,
)
from ledger_helpers import batch, descriptor_of, make

POLL = 1.0      # how long a worker without work waits before asking again


class Cluster:
    def __init__(self, candidates=6, max_attempts=3, lease_seconds=LEASE_SECONDS):
        self.env = simpy.Environment()
        self.ledger = Ledger(":memory:", clock=lambda: self.env.now, max_attempts=max_attempts)
        self.ledger.open_generation(batch(candidates))
        self.candidates = candidates
        self.max_attempts = max_attempts
        self.lease_seconds = lease_seconds
        self.log = []

    def note(self, worker, event, index, detail=""):
        self.log.append((self.env.now, worker, event, index, detail))

    def events(self, event):
        return [entry for entry in self.log if entry[2] == event]

    def status(self):
        return self.ledger.get_generation_status("exp", 0)

    def start(self, worker, behavior, dispatcher):
        self.env.process(_worker(self, worker, behavior, dispatcher))

    def run(self, limit=10_000.0):
        """Run until nothing is left to happen (or `limit`, in case a bug keeps the workers polling for ever)."""
        while self.env.peek() != float("inf") and self.env.now < limit:
            self.env.step()
        assert self.env.now < limit, "the simulation did not finish"

    def makespan(self):
        """When the last commit happened: the moment the generation became complete."""
        return max(entry[0] for entry in self.events("commit"))


def _submit(cluster, name, lease, index, descriptor=None, reward=None):
    descriptor = descriptor_of(index) if descriptor is None else descriptor
    reward = oracle_reward(descriptor_of(index).seed) if reward is None else reward
    try:
        outcome = cluster.ledger.submit_result(descriptor, lease.attempt_number, lease.token, reward)
    except LedgerError as error:
        cluster.note(name, "rejected", index, type(error).__name__)
    else:
        cluster.note(name, "commit" if outcome is SubmitOutcome.COMMITTED else "acknowledged_again", index)


def _report(cluster, name, lease, index, kind):
    cluster.ledger.report_failure(descriptor_of(index), lease.attempt_number, lease.token, kind)
    cluster.note(name, "failure", index, kind.name)


@dataclass(frozen=True)
class Behavior:
    """
    honest          computes for `compute` seconds and delivers the oracle reward
    vanish_after    honest for `after` jobs, then takes a candidate and is never heard of again
    oom             reports an out-of-memory failure half way through every job
    restore_broken  reports a failed restore after every job (it will be put aside after the first)
    lossy_ack       delivers, then delivers again (the acknowledgement was lost); `conflict`: with another reward
    wrong_job_once  delivers a result for another job first (with a wrong reward), then the honest one
    """
    kind: str = "honest"
    compute: float = 5.0
    after: int = 0
    conflict: bool = False
    wrong: str = "seed"

    def run(self, cluster, name, lease, index, jobs):
        env = cluster.env
        if self.kind == "vanish_after" and jobs > self.after:
            cluster.note(name, "vanished", index)
            return False
        if self.kind == "oom":
            yield env.timeout(self.compute / 2)
            _report(cluster, name, lease, index, FailureKind.OUT_OF_MEMORY)
            return True
        yield env.timeout(self.compute)
        if self.kind == "restore_broken":
            _report(cluster, name, lease, index, FailureKind.RESTORE_MISMATCH)
            return True

        seed = descriptor_of(index).seed
        if self.kind == "wrong_job_once" and jobs == 1:
            wrong = {"seed": make(index, seed + 1), "recipe": make(index, seed, recipe_hash="c" * 64),
                     "parent": make(index, seed, parent_weights_sha256="d" * 64)}[self.wrong]
            _submit(cluster, name, lease, index, descriptor=wrong, reward=oracle_reward(seed) + 0.5)
        _submit(cluster, name, lease, index)
        if self.kind == "lossy_ack":
            _submit(cluster, name, lease, index, reward=oracle_reward(seed) + (0.5 if self.conflict else 0.0))
        return True


def _worker(cluster, name, behavior, dispatcher):
    jobs = 0
    while True:
        if cluster.status().state is not GenerationState.OPEN:
            return                                                       # complete or failed: nothing more to do
        index = dispatcher.next_candidate(cluster, name)
        if index is None:
            yield cluster.env.timeout(POLL)
            continue
        try:
            lease = cluster.ledger.lease(f"exp/g0/c{index}", name, cluster.lease_seconds)
        except WorkerQuarantinedError:
            cluster.note(name, "quarantined", index)
            return
        except LedgerError as error:                                     # somebody else was faster, or the generation failed
            cluster.note(name, "lease_refused", index, type(error).__name__)
            yield cluster.env.timeout(POLL)
            continue
        cluster.note(name, "lease", index, f"attempt {lease.attempt_number}")
        jobs += 1
        keep_going = yield from behavior.run(cluster, name, lease, index, jobs)
        if keep_going is False:
            return


# ---- how candidates are given to workers (the policies of MASTER section 9; only these two here) ----------------------

def _available(cluster):
    """Indexes of the candidates that may be leased now, in index order (nothing running, budget left)."""
    return [i for i, record in enumerate(cluster.ledger.list_candidates("exp", 0))
            if record.state is CandidateState.PENDING and record.attempts < cluster.max_attempts]


class Greedy:
    """B3 in spirit: a worker that is free takes the next candidate."""

    def next_candidate(self, cluster, worker):
        available = _available(cluster)
        return available[0] if available else None


class Wave:
    """B1 in spirit: each wave gives at most one candidate to each worker, and the next wave waits for the whole wave."""

    def __init__(self):
        self.taken = set()

    def next_candidate(self, cluster, worker):
        records = cluster.ledger.list_candidates("exp", 0)
        if not any(record.state is CandidateState.LEASED for record in records):
            self.taken = set()                                           # nothing is running: the barrier is over
        if worker in self.taken:
            return None
        available = _available(cluster)
        if not available:
            return None
        self.taken.add(worker)
        return available[0]
