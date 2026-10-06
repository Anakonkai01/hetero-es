"""
The profile of a worker (C1, MASTER section 8): what one GPU measured about itself for ONE workload and ONE recipe.

    probe_chunks    for each number of prompts per generate() call: did it run, were the ANSWERS the same as one prompt at a
                    time (on the parent weights and on perturbed weights), how long did it take, how much memory did it use
    safe_chunk      the largest chunk that ran and gave the same answers everywhere it was tried
    summarize_times the candidate durations as a small distribution (median, spread, phases)
    profile_key     what must be equal before a profile may be reused: hardware, software, model, workload and recipe

A safe chunk is a level that was CHECKED, not a promise about every future prompt (MASTER section 8). "Same answers" means the
same text, not only the same reward: a chunk that changes the text but not the reward on 16 questions would still change the
numbers the model computes, so it is not safe for a worker that must agree with the others.
"""
import contextlib
import statistics
from dataclasses import dataclass, field

from heteroes.canonical import canonical_json_hash

PROFILE_FORMAT = 1


@dataclass(frozen=True)
class ChunkProbe:
    chunk: int
    ran: bool                       # no out-of-memory on any condition
    identical: bool | None          # the answers equal those of chunk 1 on every condition (None if it did not run)
    seconds: float | None           # mean time of one evaluation of the whole prompt set over the conditions
    peak_bytes: int | None          # largest GPU memory allocated while it ran (None if unknown, e.g. on CPU)
    error: str | None = None
    differing: tuple = field(default=())    # (condition index, question index) pairs whose text differs, for the record

    def to_dict(self) -> dict:
        return {"chunk": self.chunk, "ran": self.ran, "identical": self.identical, "seconds": self.seconds,
                "peak_bytes": self.peak_bytes, "error": self.error, "differing": [list(pair) for pair in self.differing]}


def probe_chunks(conditions, evaluate, chunks, is_oom, clock, reset_peak=lambda: None, peak_bytes=lambda: None) -> list[ChunkProbe]:
    """
    `conditions`: zero-argument context managers, each one puts the model in a state (the parent weights, a perturbed candidate)
    and puts it back on exit; the state is entered ONCE and every chunk is evaluated inside it (a perturbation costs much more
    than an evaluation, so many conditions become affordable). `evaluate(chunk)` returns the answer texts for the whole prompt
    set. The reference of a condition is chunk 1, evaluated first in the same state. A chunk 1 that does not run is a broken worker:
    the error is raised. A chunk that runs out of memory once is dropped from the following conditions.
    """
    chunks = sorted(set(chunks))
    if not chunks or chunks[0] != 1:
        raise ValueError("the chunks to probe must include 1, the reference")
    seconds = {chunk: 0.0 for chunk in chunks}
    peaks = {chunk: 0 for chunk in chunks}
    differing = {chunk: [] for chunk in chunks}
    errors: dict[int, str] = {}
    for number, condition in enumerate(conditions):
        with condition():
            reference = evaluate(1)
            for chunk in chunks:
                if chunk in errors:
                    continue
                try:
                    reset_peak()
                    start = clock()
                    texts = evaluate(chunk)
                    seconds[chunk] += clock() - start
                    peaks[chunk] = max(peaks[chunk], peak_bytes() or 0)
                except BaseException as caught:
                    if not is_oom(caught) or chunk == 1:
                        raise
                    errors[chunk] = f"{type(caught).__name__}: {caught}"
                    continue
                differing[chunk] += [(number, question) for question, (a, b) in enumerate(zip(texts, reference)) if a != b]
    probes = []
    for chunk in chunks:
        if chunk in errors:
            probes.append(ChunkProbe(chunk, False, None, None, None, errors[chunk]))
        else:
            probes.append(ChunkProbe(chunk, True, not differing[chunk], seconds[chunk] / len(conditions), peaks[chunk] or None,
                                     None, tuple(differing[chunk])))
    return probes


def safe_chunk(probes) -> int:
    """The largest chunk that ran and gave identical answers; 1 (the reference, always exact) if no other does."""
    return max([probe.chunk for probe in probes if probe.ran and probe.identical] or [1])


def summarize_times(samples: list[dict]) -> dict:
    """Candidate durations: `samples` is a list of {"perturb", "rollout", "restore", "total"} in seconds (the executor's timing)."""
    if not samples:
        raise ValueError("no sample")
    totals = [sample["total"] for sample in samples]
    summary = {"samples": len(samples), "total_median": statistics.median(totals), "total_min": min(totals), "total_max": max(totals),
               "phases_median": {phase: statistics.median(sample[phase] for sample in samples) for phase in ("perturb", "rollout", "restore")}}
    return summary


def profile_key(environment: dict, recipe_hash: str, schema_hash: str, workload_hash: str, device: str) -> dict:
    """
    Everything that must be the same for a profile to still describe this worker: the GPU, the driver, the software and the
    workload and recipe it was measured with. The time of the measurement and the numbers measured are NOT in it.
    """
    names = ("gpu_name", "gpu_capability", "gpu_total_memory_bytes", "nvidia_driver", "torch", "torch_cuda", "numpy", "transformers", "python")
    key = {name: environment.get(name) for name in names}
    key.update({"device": device, "recipe_hash": recipe_hash, "schema_hash": schema_hash, "workload_hash": workload_hash})
    return key


def key_hash(key: dict) -> str:
    return canonical_json_hash(key)


@contextlib.contextmanager
def nothing():
    yield
