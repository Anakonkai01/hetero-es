"""
Which candidate does a worker get when it asks for work? The coordinator's decision, made by a policy object.

A policy has two methods: `pick(records, worker_id)` returns the candidate (one of `records`, in index order, the ones the
ledger shows as PENDING are the only valid choice) or None for "nothing for this worker now"; `leased(candidate_id,
worker_id)` is called after the ledger gave that lease. The policies are two of the baselines of MASTER (B0 to B3, H0):

  Greedy      B3  the first candidate that is waiting goes to whoever asks (completion-driven dispatch); a candidate whose latest
                  attempt FAILED on a worker is not handed straight back to that worker while another worker is around (G6);
  GreedyTail  B4  greedy, but a slow worker is not given a candidate near the end of a generation when a faster one would finish it sooner
                  (the slow worker holding the last candidate makes everybody wait for it); it learns the speeds from the results (G6);
  StaticWave  B1  candidates are cut into waves of `wave_size` (the number of workers); a worker takes at most one candidate of
                  a wave, and the next wave begins only when every candidate of the current wave is committed;
  StaticProportional  B2  the candidates are shared out BEFORE the run, a quota per worker (`proportional_quotas`: in proportion
                  to the measured speed, the quotas add up to N); a worker runs its own candidates one after the other with no
                  waiting for the others and never takes another worker's (no stealing: that is B3, not B2);
  AdmittedOnly    not a baseline: wraps a policy and gives work only to the workers that the admission decided on.

A policy only chooses; the ledger still decides whether the lease is valid. The state of a policy lives in memory: after a
restart of the coordinator it starts empty (a wave is then not "remembered", which only matters for B1's one-per-worker rule).
"""
import math
import time

from heteroes.ledger import CandidateRecord, CandidateState


def proportional_quotas(candidates: int, speeds: dict[str, float]) -> dict[str, int]:
    """
    How many of `candidates` each worker gets, in proportion to its speed (candidates per second, measured by its profile).
    Largest-remainder rounding, so the quotas add up to `candidates` exactly; a tie in the remainder goes to the smaller worker id.
    Example: 8 candidates, speeds 4 and 1: exact shares 6.4 and 1.6, the floors 6 and 1 leave one candidate, the larger
    remainder (0.6) takes it: 6 and 2.
    """
    if isinstance(candidates, bool) or not isinstance(candidates, int) or candidates < 1:
        raise ValueError(f"candidates must be an integer of at least 1, got {candidates!r}")
    if not speeds:
        raise ValueError("there is no worker to share the candidates between")
    for worker_id, speed in speeds.items():
        if isinstance(speed, bool) or not isinstance(speed, (int, float)) or not speed > 0 or speed == float("inf"):
            raise ValueError(f"the speed of {worker_id!r} must be a positive finite number, got {speed!r}")
    total = sum(speeds.values())
    shares = {worker_id: candidates * speed / total for worker_id, speed in speeds.items()}
    quotas = {worker_id: int(share) for worker_id, share in shares.items()}          # floors
    left = candidates - sum(quotas.values())
    for worker_id in sorted(speeds, key=lambda w: (-(shares[w] - quotas[w]), w))[:left]:
        quotas[worker_id] += 1
    return quotas


class Greedy:
    """
    B3. A candidate whose latest attempt failed on worker W (an out-of-memory, a verifier error: a fault that may be W's) goes to
    another worker if there is one: W is told to wait, up to `patience` times for that candidate and failure (the other worker may
    be gone, and waiting for ever is worse than a second try on W). A worker that is alone, or that nothing else is waiting for,
    gets the candidate back at once. Candidates that did not fail on W are given to W as before.
    """

    def __init__(self, patience: int = 20):
        if isinstance(patience, bool) or not isinstance(patience, int) or patience < 1:
            raise ValueError(f"patience must be an integer of at least 1, got {patience!r}")
        self._patience = patience
        self._seen: set[str] = set()                                  # the workers that have asked for work
        self._refusals: dict[tuple[str, str, int], int] = {}          # (candidate, worker, attempts so far) -> times it was told to wait

    def pick(self, records: list[CandidateRecord], worker_id: str) -> CandidateRecord | None:
        self._seen.add(worker_id)
        pending = [record for record in records if record.state is CandidateState.PENDING]
        if not pending:
            return None
        if self._seen == {worker_id}:
            return pending[0]                                         # nobody else could take a failed candidate: the plain rule
        for record in pending:
            if record.last_failed_worker != worker_id:
                return record
        record = pending[0]                                           # every waiting candidate failed on this very worker
        key = (record.descriptor.candidate_id, worker_id, record.attempts)
        waited = self._refusals.get(key, 0)
        if waited >= self._patience:
            return record
        self._refusals[key] = waited + 1
        return None

    def leased(self, candidate_id: str, worker_id: str) -> None:
        pass


class SpeedBook:
    """
    How long a candidate takes on each worker, from lease to committed result: an exponential moving average (`alpha` is the weight of the
    newest duration). It is shared by the policies of all the generations of an experiment, so that a new generation does not start knowing nothing.
    `prior` gives starting values (for example from the profiles).
    """

    def __init__(self, alpha: float = 0.5, prior: dict[str, float] | None = None):
        if isinstance(alpha, bool) or not isinstance(alpha, (int, float)) or not 0 < alpha <= 1:
            raise ValueError(f"alpha must be a number in (0, 1], got {alpha!r}")
        self._alpha = float(alpha)
        self._estimate: dict[str, float] = {}
        for worker_id, seconds in (prior or {}).items():
            self.observe(worker_id, seconds)

    def observe(self, worker_id: str, seconds: float) -> None:
        if isinstance(seconds, bool) or not isinstance(seconds, (int, float)) or not (math.isfinite(seconds) and seconds > 0):
            raise ValueError(f"a duration must be a positive finite number of seconds, got {seconds!r}")
        old = self._estimate.get(worker_id)
        self._estimate[worker_id] = float(seconds) if old is None else self._alpha * seconds + (1 - self._alpha) * old

    def estimate(self, worker_id: str) -> float | None:
        return self._estimate.get(worker_id)

    def workers(self) -> list[str]:
        return list(self._estimate)


class GreedyTail:
    """
    B4. Like Greedy (including its rule for a candidate that just failed on a worker), with one more rule: a worker W is told to wait when the
    other workers that are alive would finish the waiting candidates sooner than W would finish this one. With `p` candidates waiting, `m` other
    workers alive and `d` the fastest of their durations, the others need about `ceil(p / m) * d` to finish them, plus up to one candidate
    that they are running now: W declines if `(ceil(p / m) + 1) * d < margin * (duration of W)`. A worker whose speed is unknown takes work (that is
    how it is learned); a worker that has not asked or delivered for `active_window` seconds is not waited for. So a slow worker works at the
    start of a generation, when many candidates are waiting, and a fast one finishes it.
    """

    def __init__(self, book: SpeedBook, clock=time.monotonic, margin: float = 1.0, active_window: float = 30.0, patience: int = 20):
        if isinstance(margin, bool) or not isinstance(margin, (int, float)) or not (math.isfinite(margin) and margin > 0):
            raise ValueError(f"margin must be a positive number, got {margin!r}")
        if isinstance(active_window, bool) or not isinstance(active_window, (int, float)) or not active_window > 0:
            raise ValueError(f"active_window must be a positive number, got {active_window!r}")
        self._book = book
        self._clock = clock
        self._margin = float(margin)
        self._window = float(active_window)
        self._inner = Greedy(patience)
        self._seen: dict[str, float] = {}                              # worker -> the last time it asked for work or delivered
        self._leased: dict[str, tuple[str, float]] = {}                # candidate id -> (worker, the time of the lease)

    def _alive(self, worker_id: str, now: float) -> bool:
        seen = self._seen.get(worker_id)
        return seen is not None and now - seen <= self._window

    def pick(self, records: list[CandidateRecord], worker_id: str) -> CandidateRecord | None:
        now = self._clock()
        self._seen[worker_id] = now
        chosen = self._inner.pick(records, worker_id)
        if chosen is None:
            return None
        mine = self._book.estimate(worker_id)
        others = [self._book.estimate(w) for w in self._seen if w != worker_id and self._alive(w, now) and self._book.estimate(w) is not None]
        if mine is None or not others:
            return chosen
        waiting = sum(1 for record in records if record.state is CandidateState.PENDING)
        others_wait = (math.ceil(waiting / len(others)) + 1) * min(others)
        return None if others_wait < self._margin * mine else chosen

    def leased(self, candidate_id: str, worker_id: str) -> None:
        self._inner.leased(candidate_id, worker_id)
        self._leased[candidate_id] = (worker_id, self._clock())

    def committed(self, candidate_id: str) -> None:
        """Called by the worker API when a result was committed (not for a repeat): the duration of that candidate teaches the book."""
        worker_id, started = self._leased.pop(candidate_id, (None, None))
        if worker_id is not None:
            now = self._clock()
            self._seen[worker_id] = now
            self._book.observe(worker_id, max(now - started, 1e-6))


class StaticWave:
    def __init__(self, wave_size: int):
        if isinstance(wave_size, bool) or not isinstance(wave_size, int):
            raise TypeError(f"wave_size must be an integer, got {type(wave_size).__name__}")
        if wave_size < 1:
            raise ValueError(f"wave_size must be at least 1, got {wave_size}")
        self._wave_size = wave_size
        self._holder: dict[str, str] = {}      # candidate id -> the worker that was given it last

    def pick(self, records: list[CandidateRecord], worker_id: str) -> CandidateRecord | None:
        for start in range(0, len(records), self._wave_size):
            wave = records[start:start + self._wave_size]
            if all(record.state is CandidateState.COMMITTED for record in wave):
                continue                                                # this wave is over
            busy = any(self._holder.get(record.descriptor.candidate_id) == worker_id
                       and record.state in (CandidateState.LEASED, CandidateState.COMMITTED) for record in wave)
            if busy:
                return None                                             # it has its candidate of this wave
            return next((record for record in wave if record.state is CandidateState.PENDING), None)
        return None

    def leased(self, candidate_id: str, worker_id: str) -> None:
        self._holder[candidate_id] = worker_id


class StaticProportional:
    def __init__(self, quotas: dict[str, int]):
        for worker_id, quota in quotas.items():
            if isinstance(quota, bool) or not isinstance(quota, int) or quota < 0:
                raise ValueError(f"the quota of {worker_id!r} must be an integer of at least 0, got {quota!r}")
        if not any(quotas.values()):
            raise ValueError("the quotas are all 0: nobody would run anything")
        self._quotas = dict(quotas)
        self._owner: dict[str, str] | None = None            # candidate id -> worker, fixed at the first request

    @property
    def quotas(self) -> dict[str, int]:
        return dict(self._quotas)

    def _assign(self, records: list[CandidateRecord]) -> dict[str, str]:
        if len(records) != sum(self._quotas.values()):
            raise ValueError(f"the quotas add up to {sum(self._quotas.values())} but the generation has {len(records)} candidates")
        owner, position = {}, 0
        for worker_id in sorted(self._quotas):              # contiguous blocks in the order of the worker ids
            for record in records[position:position + self._quotas[worker_id]]:
                owner[record.descriptor.candidate_id] = worker_id
            position += self._quotas[worker_id]
        return owner

    def pick(self, records: list[CandidateRecord], worker_id: str) -> CandidateRecord | None:
        if self._owner is None:
            self._owner = self._assign(records)
        return next((record for record in records if record.state is CandidateState.PENDING
                     and self._owner[record.descriptor.candidate_id] == worker_id), None)

    def leased(self, candidate_id: str, worker_id: str) -> None:
        pass


class AdmittedOnly:
    def __init__(self, inner, admitted):
        if isinstance(admitted, (str, bytes)) or not hasattr(admitted, "__iter__"):
            raise TypeError(f"admitted must be a collection of worker ids, got {type(admitted).__name__}")
        admitted = list(admitted)
        for worker_id in admitted:
            if not isinstance(worker_id, str):
                raise TypeError(f"a worker id must be a string, got {type(worker_id).__name__}")
            if not worker_id:
                raise ValueError("a worker id must not be empty")
        if not admitted:
            raise ValueError("no worker is admitted: every generation would wait for ever")
        self._inner = inner
        self._admitted = frozenset(admitted)

    def pick(self, records: list[CandidateRecord], worker_id: str) -> CandidateRecord | None:
        return self._inner.pick(records, worker_id) if worker_id in self._admitted else None

    def leased(self, candidate_id: str, worker_id: str) -> None:
        self._inner.leased(candidate_id, worker_id)
