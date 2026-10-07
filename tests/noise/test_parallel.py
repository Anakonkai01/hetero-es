import threading
import time

import numpy as np
import pytest

from heteroes.noise import parallel
from heteroes.noise.contracts import DEFAULT_CHUNK_ELEMENTS, ParameterNoiseAddress
from heteroes.noise.engine import generate_chunk_noise, generate_parameter_noise, iter_parameter_noise_chunks


def test_ordered_map_keeps_the_order_of_the_items_even_when_work_finishes_out_of_order():
    # item 0 is the slowest, so a pool that returned results in finishing order would put it last
    def work(i):
        time.sleep(0.05 if i == 0 else 0.0)
        return i * i

    assert list(parallel.ordered_map(work, range(20), threads=8)) == [i * i for i in range(20)]


def test_threads_1_is_plain_serial_in_the_calling_thread():
    seen = []
    list(parallel.ordered_map(lambda i: seen.append(threading.get_ident()), range(5), threads=1))
    assert set(seen) == {threading.get_ident()}


def test_parallel_really_uses_other_threads():
    # test premise: with threads > 1 the work is NOT done in the calling thread, otherwise the other tests prove nothing
    seen = set()
    list(parallel.ordered_map(lambda i: seen.add(threading.get_ident()), range(40), threads=4))
    assert threading.get_ident() not in seen


def test_the_window_bounds_how_far_the_work_runs_ahead_of_the_consumer():
    started = []
    lock = threading.Lock()

    def work(i):
        with lock:
            started.append(i)
        return i

    it = parallel.ordered_map(work, range(1000), threads=4, window=6)
    next(it)
    time.sleep(0.1)
    with lock:
        ahead = len(started)
    it.close()
    assert ahead <= 7  # one consumed + the window
    assert ahead < 1000


def test_an_exception_in_a_worker_thread_reaches_the_consumer_in_order():
    def work(i):
        if i == 3:
            raise RuntimeError("boom 3")
        return i

    it = parallel.ordered_map(work, range(10), threads=4)
    assert [next(it) for _ in range(3)] == [0, 1, 2]
    with pytest.raises(RuntimeError, match="boom 3"):
        next(it)


def test_closing_the_generator_early_stops_new_work():
    count = []

    def work(i):
        count.append(i)
        time.sleep(0.01)
        return i

    it = parallel.ordered_map(work, range(10_000), threads=4, window=8)
    next(it)
    it.close()
    time.sleep(0.2)
    settled = len(count)
    time.sleep(0.2)
    assert len(count) == settled
    assert settled < 100


def test_empty_input():
    assert list(parallel.ordered_map(lambda i: i, [], threads=4)) == []


def test_invalid_arguments():
    with pytest.raises(ValueError):
        list(parallel.ordered_map(lambda i: i, [1], threads=0))
    with pytest.raises(ValueError):
        list(parallel.ordered_map(lambda i: i, [1], threads=2, window=0))


@pytest.mark.parametrize("value,expected", [("1", 1), ("7", 7), ("  3 ", 3)])
def test_noise_threads_reads_the_environment(monkeypatch, value, expected):
    monkeypatch.setenv(parallel.ENV_THREADS, value)
    assert parallel.noise_threads() == expected


@pytest.mark.parametrize("value", ["0", "-2", "many", "", "1.5"])
def test_noise_threads_rejects_a_bad_environment_value(monkeypatch, value):
    monkeypatch.setenv(parallel.ENV_THREADS, value)
    with pytest.raises(ValueError, match=parallel.ENV_THREADS):
        parallel.noise_threads()


def test_noise_threads_default_is_between_1_and_the_cap(monkeypatch):
    monkeypatch.delenv(parallel.ENV_THREADS, raising=False)
    assert 1 <= parallel.noise_threads() <= parallel.MAX_DEFAULT_THREADS


# the noise itself must not change by one bit


def _address():
    return ParameterNoiseAddress(candidate_seed=11, schema_hash="ab" * 32, parameter_index=3, chunk_elements=64)


@pytest.mark.parametrize("numel", [1, 63, 64, 65, 1000, 64 * 17 + 5])
@pytest.mark.parametrize("threads", ["1", "4"])
def test_parallel_parameter_noise_is_bit_identical_to_chunk_by_chunk_generation(monkeypatch, numel, threads):
    monkeypatch.setenv(parallel.ENV_THREADS, threads)
    addr = _address()
    # oracle: the single-chunk function, called one chunk at a time, no pool involved
    expected = np.concatenate(
        [
            generate_chunk_noise(addr.chunk(i), min(64, numel - i * 64))
            for i in range(-(-numel // 64))
        ]
    )
    got = generate_parameter_noise(addr, numel)
    assert got.dtype == np.float16
    assert got.view(np.uint16).tobytes() == expected.view(np.uint16).tobytes()
    chunks = list(iter_parameter_noise_chunks(addr, numel))
    assert [c[0] for c in chunks] == list(range(len(chunks)))
    assert [c[1] for c in chunks] == [i * 64 for i in range(len(chunks))]


def test_default_chunk_size_is_unchanged():
    # the parallel path must not touch the contract value
    assert DEFAULT_CHUNK_ELEMENTS == 2**18
