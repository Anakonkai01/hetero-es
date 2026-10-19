"""The thread pool of the noise generation must change the speed and nothing else: same weights bit for bit,
same report, same perturbation, for any number of threads."""

import numpy as np
import pytest
import torch
import torch.nn as nn

from heteroes.es.perturb import perturb_model_
from heteroes.es.update import apply_coefficients_
from heteroes.model.schema import build_parameter_schema
from heteroes.noise import parallel

DEVICES = ["cpu"] + (["cuda"] if torch.cuda.is_available() else [])


class Toy(nn.Module):
    def __init__(self):
        super().__init__()
        torch.manual_seed(0)
        self.a = nn.Linear(37, 53)
        self.b = nn.Linear(53, 11)
        self.half()


def _bits(model):
    return b"".join(p.detach().cpu().view(torch.int16).numpy().tobytes() for p in model.parameters())


def _run(device, threads, monkeypatch, chunk_elements):
    monkeypatch.setenv(parallel.ENV_THREADS, str(threads))
    model = Toy().to(device)
    schema = build_parameter_schema(model)
    perturb_model_(model, schema, candidate_seed=5, sigma=1e-3, chunk_elements=chunk_elements)
    after_perturb = _bits(model)
    seeds = [3, 9, 21, 4, 17]
    z = np.array([1.2, -0.7, 0.3, -1.1, 0.25], dtype=np.float32)
    report = apply_coefficients_(model, schema, seeds, z, alpha=1e-1, chunk_elements=chunk_elements)
    return after_perturb, _bits(model), report


@pytest.mark.parametrize("device", DEVICES)
@pytest.mark.parametrize("chunk_elements", [7, 64, 1000])
def test_perturb_and_update_are_bit_identical_for_1_and_many_threads(device, chunk_elements, monkeypatch):
    one = _run(device, 1, monkeypatch, chunk_elements)
    many = _run(device, 8, monkeypatch, chunk_elements)
    assert one[0] == many[0]
    assert one[1] == many[1]
    assert one[2] == many[2]  # UpdateReport is a frozen dataclass: exact equality of every float
    assert one[0] != one[1]  # premise: the update really changed something
    assert one[2].changed > 0


@pytest.mark.parametrize("device", DEVICES)
def test_the_update_reports_the_same_chunk_statistics_as_summing_them_one_by_one(device, monkeypatch):
    # oracle for the report, written without the batching: requested_l2 = ||update||, applied_l2 = ||new - old||
    monkeypatch.setenv(parallel.ENV_THREADS, "4")
    model = Toy().to(device)
    schema = build_parameter_schema(model)
    before = _bits(model)
    seeds = [1, 2, 3]
    z = np.array([1.0, -1.0, 0.5], dtype=np.float32)
    report = apply_coefficients_(model, schema, seeds, z, alpha=0.05, chunk_elements=50)
    after = _bits(model)
    changed = sum(x != y for x, y in zip(np.frombuffer(before, np.int16), np.frombuffer(after, np.int16)))
    assert report.changed == changed
    assert report.numel == sum(p.numel() for p in model.parameters())
    assert report.applied_l2 > 0 and report.requested_l2 > 0


@pytest.mark.parametrize("device", DEVICES)
@pytest.mark.parametrize("batch", [1, 7, 64, 1000, 10**9])
def test_the_size_of_the_pieces_sent_to_the_device_does_not_change_a_bit(device, batch, monkeypatch):
    import heteroes.es.perturb as perturb_module

    def perturbed_bits(batch_elements):
        monkeypatch.setattr(perturb_module, "BATCH_ELEMENTS", batch_elements)
        model = Toy().to(device)
        perturb_model_(model, build_parameter_schema(model), candidate_seed=5, sigma=1e-3, chunk_elements=16)    # many chunks per tensor
        return _bits(model)

    assert perturbed_bits(batch) == perturbed_bits(2**22)


@pytest.mark.parametrize("device", DEVICES)
@pytest.mark.parametrize("batch", [1, 16, 100, 10**9])
@pytest.mark.parametrize("chunk_elements", [7, 64])
def test_the_size_of_the_pieces_of_the_update_does_not_change_a_bit(device, batch, chunk_elements, monkeypatch):
    import heteroes.es.perturb as perturb_module

    def updated(batch_elements):
        monkeypatch.setattr(perturb_module, "BATCH_ELEMENTS", batch_elements)
        model = Toy().to(device)
        schema = build_parameter_schema(model)
        seeds = [3, 9, 21, 4, 17]
        z = np.array([1.2, -0.7, 0.3, -1.1, 0.25], dtype=np.float32)
        report = apply_coefficients_(model, schema, seeds, z, alpha=1e-1, chunk_elements=chunk_elements)
        return _bits(model), report.changed

    assert updated(batch) == updated(2**22)


@pytest.mark.parametrize("device", DEVICES)
def test_the_noise_goes_to_the_device_in_pieces_of_about_the_batch_size_not_all_at_once(device, monkeypatch):
    # an equivalent change in bits but not in memory: a whole 136M-element embedding in one piece would need gigabytes on the 6 GB card
    import heteroes.es.perturb as perturb_module

    pieces = []
    real = perturb_module.np.concatenate
    monkeypatch.setattr(perturb_module, "BATCH_ELEMENTS", 64)
    monkeypatch.setattr(perturb_module.np, "concatenate", lambda arrays, *a, **k: (pieces.append(sum(x.size for x in arrays)), real(arrays, *a, **k))[1])
    model = Toy().to(device)
    perturb_model_(model, build_parameter_schema(model), candidate_seed=5, sigma=1e-3, chunk_elements=16)
    assert pieces and max(pieces) <= 64 + 15                  # a piece is closed as soon as it holds at least 64 elements: at most 64 + one chunk
    assert len(pieces) >= 20                                  # 37*53 + 53*11 weights are many pieces, not one
