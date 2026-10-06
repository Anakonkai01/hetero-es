"""
Which candidate does a worker get when it asks for work? The coordinator's decision, made by a policy object.

A policy has two methods: `pick(records, worker_id)` returns the candidate (one of `records`, in index order, the ones the
ledger shows as PENDING are the only valid choice) or None for "nothing for this worker now"; `leased(candidate_id,
worker_id)` is called after the ledger gave that lease. The policies are two of the baselines of MASTER (B0 to B3, H0):

  Greedy      B3  the first candidate that is waiting goes to whoever asks (completion-driven dispatch);
  StaticWave  B1  candidates are cut into waves of `wave_size` (the number of workers); a worker takes at most one candidate of
                  a wave, and the next wave begins only when every candidate of the current wave is committed;
  StaticProportional  B2  the candidates are shared out BEFORE the run, a quota per worker (`proportional_quotas`: in proportion
                  to the measured speed, the quotas add up to N); a worker runs its own candidates one after the other with no
                  waiting for the others and never takes another worker's (no stealing: that is B3, not B2);
  AdmittedOnly    not a baseline: wraps a policy and gives work only to the workers that the admission decided on.

A policy only chooses; the ledger still decides whether the lease is valid. The state of a policy lives in memory: after a
restart of the coordinator it starts empty (a wave is then not "remembered", which only matters for B1's one-per-worker rule).
"""
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
    def pick(self, records: list[CandidateRecord], worker_id: str) -> CandidateRecord | None:
        return next((record for record in records if record.state is CandidateState.PENDING), None)

    def leased(self, candidate_id: str, worker_id: str) -> None:
        pass


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
        self._inner = inner
        self._admitted = frozenset(admitted)

    def pick(self, records: list[CandidateRecord], worker_id: str) -> CandidateRecord | None:
        return self._inner.pick(records, worker_id) if worker_id in self._admitted else None

    def leased(self, candidate_id: str, worker_id: str) -> None:
        self._inner.leased(candidate_id, worker_id)
