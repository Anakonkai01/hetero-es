"""
Run the (pure) noise generation of many chunks in parallel and hand the results back IN ORDER.

Why this is safe for the numerical contract: the noise of a chunk depends only on its address
(schema hash, engine version, candidate seed, parameter index, chunk index, chunk size), never on
which thread made it or when. Parallelism only changes WHEN a chunk is generated; the consumer still
receives the chunks in the original order, so every later floating-point operation (the perturbation,
the sum over candidates in the update) happens in exactly the same order as before.

Why threads work: NumPy's Generator releases the GIL while it fills an array (measured 07/10/2026:
200 chunks in 0.41 s serial, 0.031 s with 24 threads).
"""

import os
import threading
from collections import deque
from collections.abc import Callable, Iterable, Iterator
from concurrent.futures import ThreadPoolExecutor
from typing import TypeVar

ENV_THREADS = "HETEROES_NOISE_THREADS"
# a coordinator and a local worker share one CPU, so do not take all of it by default
MAX_DEFAULT_THREADS = 8

T = TypeVar("T")
R = TypeVar("R")

_pools: dict[int, ThreadPoolExecutor] = {}
_pools_lock = threading.Lock()


def noise_threads() -> int:
    """Number of threads for noise generation: HETEROES_NOISE_THREADS if set (>= 1), else min(8, CPUs)."""
    raw = os.environ.get(ENV_THREADS)
    if raw is None:
        return max(1, min(MAX_DEFAULT_THREADS, os.cpu_count() or 1))
    try:
        value = int(raw.strip())
    except ValueError:
        raise ValueError(f"{ENV_THREADS} must be an integer >= 1, got {raw!r}") from None
    if value < 1:
        raise ValueError(f"{ENV_THREADS} must be an integer >= 1, got {raw!r}")
    return value


def _pool(threads: int) -> ThreadPoolExecutor:
    with _pools_lock:
        pool = _pools.get(threads)
        if pool is None:
            pool = ThreadPoolExecutor(max_workers=threads, thread_name_prefix="heteroes-noise")
            _pools[threads] = pool
        return pool


def ordered_map(fn: Callable[[T], R], items: Iterable[T], threads: int | None = None, window: int | None = None) -> Iterator[R]:
    """
    Like `map(fn, items)`, results in the order of `items`, but `fn` runs on a thread pool, at most
    `window` items ahead of the consumer (default 4 * threads), so memory stays bounded.

    - threads == 1: plain serial map in the calling thread (no pool).
    - An exception raised by `fn` is raised to the consumer at that item's position.
    - Closing the generator early cancels the work that has not started.
    """
    if threads is None:
        threads = noise_threads()
    if not (isinstance(threads, int) and threads >= 1):
        raise ValueError("threads must be an integer >= 1")
    if window is None:
        window = 4 * threads
    if not (isinstance(window, int) and window >= 1):
        raise ValueError("window must be an integer >= 1")

    if threads == 1:
        for item in items:
            yield fn(item)
        return

    pool = _pool(threads)
    source = iter(items)
    pending: deque = deque()
    try:
        for item in source:
            pending.append(pool.submit(fn, item))
            if len(pending) >= window:
                break
        while pending:
            result = pending.popleft().result()
            for item in source:
                pending.append(pool.submit(fn, item))
                break
            yield result
    finally:
        for future in pending:
            future.cancel()
