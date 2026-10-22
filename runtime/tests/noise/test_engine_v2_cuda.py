"""Engine v2 made on a CUDA device must give the bits of the CPU engine; the CPU parts run everywhere."""

import hashlib

import numpy as np
import pytest
import torch
import torch.nn as nn

from heteroes.es import perturb as perturb_module
from heteroes.es.perturb import perturb_model_
from heteroes.es.update import apply_coefficients_
from heteroes.model.schema import build_parameter_schema
from heteroes.noise import engine_v2_cuda
from heteroes.noise.contracts import ENGINE_V2, ChunkNoiseAddress
from heteroes.noise.engine_v2 import derive_chunk_seed, generate_chunk_noise

GPU = pytest.mark.skipif(not torch.cuda.is_available(), reason="needs a CUDA GPU")


def xsl_rr(state):
    hi, lo = state >> 64, state & (2**64 - 1)
    x, r = hi ^ lo, hi >> 58
    return ((x >> r) | (x << ((64 - r) & 63))) & (2**64 - 1)


@pytest.mark.parametrize("candidate_seed,chunk", [(0, 0), (2**63 - 1, 9), (12345, 3)])
def test_jump_ahead_tables_and_states_reproduce_numpy_pcg64_words(candidate_seed, chunk):
    address = ChunkNoiseAddress(candidate_seed, "schema", 4, chunk, 2**18)
    words = 300
    expected = np.random.PCG64(derive_chunk_seed(address)).random_raw(words)
    tables = engine_v2_cuda.jump_tables(words).view(np.uint64)
    state = engine_v2_cuda.chunk_states([address]).view(np.uint64)[0]
    s0, inc = int(state[0]) | int(state[1]) << 64, int(state[2]) | int(state[3]) << 64
    for m in range(words):
        a = int(tables[0, m]) | int(tables[1, m]) << 64
        b = int(tables[2, m]) | int(tables[3, m]) << 64
        assert xsl_rr((a * s0 + b * inc) % 2**128) == int(expected[m])


def test_the_path_is_off_for_cpu_tensors_and_when_asked(monkeypatch):
    assert engine_v2_cuda.enabled(torch.device("cpu")) is False
    monkeypatch.setenv(engine_v2_cuda.ENV_DEVICE, "cpu")
    assert engine_v2_cuda.enabled(torch.device("cuda", 0)) is False


@GPU
def test_device_chunks_have_the_cpu_bits_including_tails_and_small_chunks():
    rng = np.random.default_rng(23)
    cases = [(2**18, [2**18] * 5 + [2**18 - 1]), (1000, [1000, 1000, 7]), (3, [3, 1])]
    for chunk_elements, lengths in cases:
        addresses = [
            ChunkNoiseAddress(int(rng.integers(0, 2**63)), "s", int(rng.integers(0, 500)), i, chunk_elements)
            for i in range(len(lengths))
        ]
        made = engine_v2_cuda.generate_chunks(addresses, lengths, torch.device("cuda")).cpu().numpy()
        expected = np.concatenate([generate_chunk_noise(a, n) for a, n in zip(addresses, lengths)])
        assert np.array_equal(made.view(np.uint16), expected.view(np.uint16))
    assert engine_v2_cuda.selftest(torch.device("cuda"))


class Toy(nn.Module):
    def __init__(self):
        super().__init__()
        self.embed = nn.Embedding(300, 700)  # 210,000 elements: several chunks of 2**16 and a tail
        self.fc = nn.Linear(700, 3)
        self.half()


def digest(model):
    h = hashlib.sha256()
    for p in model.parameters():
        h.update(p.detach().cpu().contiguous().view(torch.int16).numpy().tobytes())
    return h.hexdigest()


@GPU
@pytest.mark.parametrize("chunk_elements", [2**16, 1000])
def test_perturb_and_update_on_the_device_equal_the_cpu_noise_path(monkeypatch, chunk_elements):
    monkeypatch.setattr(perturb_module, "BATCH_ELEMENTS", 3 * chunk_elements)  # several pieces per tensor
    torch.manual_seed(0)
    base = Toy().cuda()
    schema = build_parameter_schema(base)
    results = {}
    for mode in ("cuda", "cpu"):
        monkeypatch.setenv(engine_v2_cuda.ENV_DEVICE, mode)
        model = Toy().cuda()
        model.load_state_dict(base.state_dict())
        perturb_model_(model, schema, 77, 0.01, chunk_elements, engine=ENGINE_V2)
        apply_coefficients_(
            model,
            schema,
            [5, 6, 9, 11, 12, 30, 31, 40, 41],
            [1.0, -0.5, 0.25, 2.0, -1.0, 0.5, 0.125, -2.0, 1.5],
            0.01,
            chunk_elements,
            engine=ENGINE_V2,
        )
        results[mode] = digest(model)
    assert results["cuda"] == results["cpu"]
    assert results["cuda"] != digest(base)
