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
