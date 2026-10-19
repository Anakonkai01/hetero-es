from heteroes.ledger import FailureKind
from heteroes.manifest import CandidateDescriptor

RECIPE = "a" * 64
PARENT = "b" * 64


def make(index, seed, **changes):
    values = dict(recipe_hash=RECIPE, parent_weights_sha256=PARENT, experiment_id="exp", generation=0,
                  index=index, seed=seed)
    values.update(changes)
    return CandidateDescriptor(**values)


class FakeClock:
    """Time that only moves when the test says so (binary fractions, so the sums are exact)."""

    def __init__(self, now=1000.0):
        self.now = now

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


def descriptor_of(index):
    return make(index, 1000 + 7 * index)


def batch(n=3, **changes):
    return [make(i, 1000 + 7 * i, **changes) for i in range(n)]


def lease(ledger, index=0, worker="worker-a", duration=30.0):
    return ledger.lease(f"exp/g0/c{index}", worker, duration)


def _index_of(lease_):
    return int(lease_.candidate_id.rsplit("/c", 1)[1])


def submit(ledger, lease_, reward=0.5, descriptor=None):
    """Submit the way a worker does: the job it ran, the attempt, the token, the reward."""
    if descriptor is None:
        descriptor = descriptor_of(_index_of(lease_))
    return ledger.submit_result(descriptor, lease_.attempt_number, lease_.token, reward)


def fail(ledger, lease_, kind=FailureKind.OTHER, descriptor=None):
    if descriptor is None:
        descriptor = descriptor_of(_index_of(lease_))
    return ledger.report_failure(descriptor, lease_.attempt_number, lease_.token, kind)


def record(ledger, index=0):
    return ledger.get_candidate(f"exp/g0/c{index}")
