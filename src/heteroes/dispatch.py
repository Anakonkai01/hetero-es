"""
Which candidate does a worker get when it asks for work? The coordinator's decision, made by a policy object.

A policy has two methods: `pick(records, worker_id)` returns the candidate (one of `records`, in index order, the ones the
ledger shows as PENDING are the only valid choice) or None for "nothing for this worker now"; `leased(candidate_id,
worker_id)` is called after the ledger gave that lease. The policies are two of the baselines of MASTER (B0 to B3, H0):

  Greedy      B3  the first candidate that is waiting goes to whoever asks (completion-driven dispatch);
  StaticWave  B1  candidates are cut into waves of `wave_size` (the number of workers); a worker takes at most one candidate of
                  a wave, and the next wave begins only when every candidate of the current wave is committed.

A policy only chooses; the ledger still decides whether the lease is valid. The state of a policy lives in memory: after a
restart of the coordinator it starts empty (a wave is then not "remembered", which only matters for B1's one-per-worker rule).
"""
from heteroes.ledger import CandidateRecord, CandidateState


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
