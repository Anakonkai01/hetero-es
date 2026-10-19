import copy
import hashlib
import os

import numpy as np
import pytest
import torch
import torch.nn as nn

from heteroes.es.snapshot import diff_from_snapshot, restore_from_snapshot_, take_snapshot
from heteroes.es.update import apply_es_update_
from heteroes.model.schema import SchemaMismatchError, build_parameter_schema, resolve_tensors
from heteroes.noise.contracts import DEFAULT_CHUNK_ELEMENTS, ParameterNoiseAddress
from heteroes.noise.engine import generate_parameter_noise

DEVICES = ["cpu"] + (["cuda"] if torch.cuda.is_available() else [])
ETA = 1e-9


class HalfToy(nn.Module):
    # FP16 model in miniature. Canonical order: embed.weight (40, tied with head.weight),
    # fc.weight (16), fc.bias (4); optionally a bad tensor LAST (in a child module).
    def __init__(self, bad_last=None):
        super().__init__()
        self.embed = nn.Embedding(10, 4)
        self.head = nn.Linear(4, 10, bias=False)
        self.head.weight = self.embed.weight
        self.fc = nn.Linear(4, 4)
        self.half()
        if bad_last is not None:
            self.tail = nn.Module()
            if bad_last == "non_contiguous":
                self.tail.w = nn.Parameter(torch.zeros(4, 3, dtype=torch.float16).t())
            elif bad_last == "float32":
                self.tail.w = nn.Parameter(torch.zeros(3, dtype=torch.float32))


class Big(nn.Module):
    # One big FP16 tensor, so that rare floating-point effects show up.
    def __init__(self, numel=200_000):
        super().__init__()
        self.w = nn.Parameter((torch.randn(numel) * 0.02).half())


def make_model(bad_last=None, device="cpu"):
    torch.manual_seed(0)
    model = HalfToy(bad_last)
    assert model.head.weight is model.embed.weight
    return model.to(device)


def make_big(device="cpu"):
    torch.manual_seed(1)
    return Big().to(device)


def snapshot_bits(model):
    return [p.detach().cpu().reshape(-1).view(torch.int16).clone() for p in model.parameters()]


def same_bits(model, reference):
    return all(torch.equal(a, b) for a, b in zip(snapshot_bits(model), reference))


def bits(array):
    return np.asarray(array).view(np.int16)


# ---------------------------------------------------------------------------
# independent oracle, written straight from numerical-contract.md section 8 with NumPy
# ---------------------------------------------------------------------------

def oracle_z(rewards, eta=ETA):
    r = np.asarray(rewards, dtype=np.float64)
    mu, s = r.mean(), r.std()
    return np.zeros(len(r), np.float32) if s < eta else ((r - mu) / (s + eta)).astype(np.float32)


def oracle_new_tensor(theta, schema, index, seeds, z, alpha, chunk_elements):
    # direction = sum_i z_i * eps_i in FP32, in the order given; divide by N; scale by alpha;
    # add to theta in FP32; cast to FP16 ONCE. Every operation is a separate NumPy call.
    numel = theta.size
    acc = np.zeros(numel, np.float32)
    for seed, zi in zip(seeds, z):
        address = ParameterNoiseAddress(seed, schema.hash, index, chunk_elements)
        eps = generate_parameter_noise(address, numel).astype(np.float32)  # canonical FP16 -> FP32 (O4)
        acc = acc + np.float32(zi) * eps
    direction = acc / np.float32(len(seeds))
    update = np.float32(alpha) * direction
    return (theta.astype(np.float32) + update).astype(np.float16), update


def oracle_model(model, schema, seeds, rewards, alpha, chunk_elements):
    z = oracle_z(rewards)
    new, updates = [], []
    for entry, tensor in zip(schema.entries, resolve_tensors(model, schema)):
        theta = tensor.detach().cpu().numpy().reshape(-1)
        n, u = oracle_new_tensor(theta, schema, entry.index, seeds, z, alpha, chunk_elements)
        new.append(n.reshape(entry.shape))
        updates.append(u)
    return new, updates


def naive_fp16_accumulation(theta, schema, index, seeds, z, alpha, chunk_elements):
    # The known mistake of the old notebook: accumulating the direction in FP16.
    numel = theta.size
    acc = np.zeros(numel, np.float16)
    for seed, zi in zip(seeds, z):
        eps = generate_parameter_noise(ParameterNoiseAddress(seed, schema.hash, index, chunk_elements), numel)
        acc = acc + np.float16(zi) * eps
    return (theta + np.float16(alpha) * (acc / np.float16(len(seeds)))).astype(np.float16)


SEEDS = [0, 1, 2, 3]
REWARDS = [0.1, 0.4, 0.2, 0.9]


# ---------------------------------------------------------------------------
# correctness against the oracle
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("device", DEVICES)
@pytest.mark.parametrize("chunk_elements", [4, 16, DEFAULT_CHUNK_ELEMENTS])
def test_every_tensor_matches_the_numpy_oracle(chunk_elements, device):
    model = make_model(device=device)
    schema = build_parameter_schema(model)
    expected, _ = oracle_model(model, schema, SEEDS, REWARDS, 0.05, chunk_elements)

    apply_es_update_(model, schema, SEEDS, REWARDS, alpha=0.05, chunk_elements=chunk_elements)

    for tensor, want in zip(resolve_tensors(model, schema), expected):
        assert np.array_equal(bits(tensor.detach().cpu().numpy()), bits(want))


@pytest.mark.skipif("cuda" not in DEVICES, reason="needs a CUDA GPU")
def test_cpu_and_gpu_give_the_same_bits():
    cpu, gpu = make_model(), make_model(device="cuda")
    for model in (cpu, gpu):
        apply_es_update_(model, build_parameter_schema(model), SEEDS, REWARDS, alpha=0.05, chunk_elements=16)

    assert all(torch.equal(a.cpu(), b.cpu()) for a, b in zip(cpu.parameters(), gpu.parameters()))


def test_a_tied_tensor_is_updated_exactly_once():
    model = make_model()
    schema = build_parameter_schema(model)
    theta = model.embed.weight.detach().numpy().reshape(-1).copy()
    once, _ = oracle_new_tensor(theta, schema, 0, SEEDS, oracle_z(REWARDS), 0.05, 8)

    apply_es_update_(model, schema, SEEDS, REWARDS, alpha=0.05, chunk_elements=8)

    assert np.array_equal(bits(model.embed.weight.detach().numpy().reshape(-1)), bits(once))
    assert model.head.weight is model.embed.weight


# ---------------------------------------------------------------------------
# FP32 accumulation and candidate order: these only show on bigger data
# ---------------------------------------------------------------------------

BIG_SEEDS = list(range(8))
BIG_REWARDS = [0.1, 0.4, 0.2, 0.9, 0.3, 0.5, 0.0, 0.7]
BIG_CHUNK = 65_536


def big_expected(model, schema, seeds, rewards):
    theta = model.w.detach().numpy().copy()
    return oracle_new_tensor(theta, schema, 0, seeds, oracle_z(rewards), 0.05, BIG_CHUNK)[0]


def test_accumulation_is_done_in_fp32_not_fp16():
    model = make_big()
    schema = build_parameter_schema(model)
    theta = model.w.detach().numpy().copy()
    correct = big_expected(model, schema, BIG_SEEDS, BIG_REWARDS)
    naive = naive_fp16_accumulation(theta, schema, 0, BIG_SEEDS, oracle_z(BIG_REWARDS), 0.05, BIG_CHUNK)
    assert np.count_nonzero(bits(correct) != bits(naive)) > 1000  # premise: this data tells them apart

    apply_es_update_(model, schema, BIG_SEEDS, BIG_REWARDS, alpha=0.05, chunk_elements=BIG_CHUNK)

    assert np.array_equal(bits(model.w.detach().numpy()), bits(correct))


def test_candidates_are_summed_in_the_order_given_not_sorted():
    # Floating-point addition is not associative, so the order is part of the result.
    model_a, model_b = make_big(), make_big()
    schema = build_parameter_schema(model_a)
    perm = [3, 1, 7, 0, 5, 2, 6, 4]
    seeds_b = [BIG_SEEDS[i] for i in perm]
    rewards_b = [BIG_REWARDS[i] for i in perm]
    expected_a = big_expected(model_a, schema, BIG_SEEDS, BIG_REWARDS)
    expected_b = big_expected(model_b, schema, seeds_b, rewards_b)
    assert np.count_nonzero(bits(expected_a) != bits(expected_b)) > 0  # premise: order changes bits

    apply_es_update_(model_a, schema, BIG_SEEDS, BIG_REWARDS, alpha=0.05, chunk_elements=BIG_CHUNK)
    apply_es_update_(model_b, schema, seeds_b, rewards_b, alpha=0.05, chunk_elements=BIG_CHUNK)

    assert np.array_equal(bits(model_a.w.detach().numpy()), bits(expected_a))
    assert np.array_equal(bits(model_b.w.detach().numpy()), bits(expected_b))


# ---------------------------------------------------------------------------
# equal rewards: a logged no-op
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("rewards", [[0.5] * 4, [0.0] * 4])
def test_equal_rewards_leave_the_model_untouched_and_say_so(rewards):
    model = make_model()
    schema = build_parameter_schema(model)
    before = snapshot_bits(model)

    report = apply_es_update_(model, schema, SEEDS, rewards, alpha=0.05)

    assert same_bits(model, before)
    assert report.noop is True
    assert report.coefficients == (0.0, 0.0, 0.0, 0.0)
    assert report.changed == 0
    assert report.requested_l2 == 0.0 and report.applied_l2 == 0.0


# ---------------------------------------------------------------------------
# report: requested versus actually applied update
# ---------------------------------------------------------------------------

def test_report_describes_the_requested_and_the_applied_update():
    model = make_model()
    schema = build_parameter_schema(model)
    before = [t.detach().numpy().reshape(-1).copy() for t in resolve_tensors(model, schema)]
    expected, updates = oracle_model(model, schema, SEEDS, REWARDS, 0.05, 8)

    report = apply_es_update_(model, schema, SEEDS, REWARDS, alpha=0.05, chunk_elements=8)

    applied = [n.reshape(-1).astype(np.float64) - b.astype(np.float64) for n, b in zip(expected, before)]
    assert report.noop is False
    assert report.coefficients == tuple(float(v) for v in oracle_z(REWARDS))
    assert report.numel == sum(b.size for b in before) == 60
    assert report.changed == sum(int(np.count_nonzero(n.reshape(-1) != b)) for n, b in zip(expected, before))
    assert 0 < report.changed <= report.numel
    assert report.requested_l2 == pytest.approx(
        float(np.sqrt(sum((u.astype(np.float64) ** 2).sum() for u in updates))), rel=1e-5
    )
    assert report.applied_l2 == pytest.approx(float(np.sqrt(sum((a**2).sum() for a in applied))), rel=1e-5)


# ---------------------------------------------------------------------------
# all or nothing: bad input is rejected BEFORE any tensor is changed
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "kwargs",
    [
        pytest.param(dict(rewards=[0.1, float("nan"), 0.2, 0.3]), id="nan reward"),
        pytest.param(dict(rewards=[0.1, float("inf"), 0.2, 0.3]), id="inf reward"),
        pytest.param(dict(rewards=[0.1, 0.2, 0.3]), id="fewer rewards than seeds"),
        pytest.param(dict(seeds=[0, 1, 2]), id="fewer seeds than rewards"),
        pytest.param(dict(seeds=[], rewards=[]), id="no candidates"),
        pytest.param(dict(seeds=[0, 1, 1, 3]), id="duplicate seeds"),
        pytest.param(dict(alpha=float("nan")), id="nan alpha"),
        pytest.param(dict(alpha=float("inf")), id="inf alpha"),
        pytest.param(dict(eta=0.0), id="eta zero"),
        pytest.param(dict(eta=float("nan")), id="eta nan"),
    ],
)
def test_bad_arguments_are_rejected_and_the_model_untouched(kwargs):
    model = make_model()
    schema = build_parameter_schema(model)
    before = snapshot_bits(model)
    arguments = dict(seeds=SEEDS, rewards=REWARDS, alpha=0.05)
    arguments.update(kwargs)

    with pytest.raises(ValueError):
        apply_es_update_(model, schema, arguments.pop("seeds"), arguments.pop("rewards"), **arguments)

    assert same_bits(model, before)


@pytest.mark.parametrize(
    "bad_seed",
    [
        pytest.param(1.0, id="float"),
        pytest.param(True, id="bool"),
        pytest.param("1", id="str"),
        pytest.param(None, id="None"),
    ],
)
def test_a_seed_that_is_not_a_real_integer_is_rejected_and_the_model_untouched(bad_seed):
    # The engine turns the seed into text, so 1 and "1" give the SAME noise, while 1 and 1.0 or True give
    # different noise. A set-based duplicate check would be wrong in both directions, so the type is checked first.
    # Wrong type -> TypeError (like a wrong dtype); duplicate value -> ValueError.
    model = make_model()
    schema = build_parameter_schema(model)
    before = snapshot_bits(model)

    with pytest.raises(TypeError):
        apply_es_update_(model, schema, [0, bad_seed, 2, 3], REWARDS, alpha=0.05)

    assert same_bits(model, before)


def test_a_string_seed_is_not_silently_a_duplicate_of_the_same_integer():
    # [1, "1"] would produce identical noise for two candidates; it must be refused, not applied.
    model = make_model()
    schema = build_parameter_schema(model)
    before = snapshot_bits(model)

    with pytest.raises(TypeError):
        apply_es_update_(model, schema, [1, "1", 2, 3], REWARDS, alpha=0.05)

    assert same_bits(model, before)


def test_numpy_integer_seeds_give_the_same_result_as_python_integers():
    # The engine prints np.int64(1) exactly like 1, so they are the same candidate.
    plain, numpy_seeds = make_model(), make_model()
    schema = build_parameter_schema(plain)

    apply_es_update_(plain, schema, SEEDS, REWARDS, alpha=0.05, chunk_elements=8)
    apply_es_update_(numpy_seeds, schema, [np.int64(s) for s in SEEDS], REWARDS, alpha=0.05, chunk_elements=8)

    assert all(torch.equal(a, b) for a, b in zip(plain.parameters(), numpy_seeds.parameters()))


def test_a_numpy_integer_is_a_duplicate_of_the_same_python_integer():
    model = make_model()
    schema = build_parameter_schema(model)
    before = snapshot_bits(model)

    with pytest.raises(ValueError):
        apply_es_update_(model, schema, [1, np.int64(1), 2, 3], REWARDS, alpha=0.05)

    assert same_bits(model, before)


@pytest.mark.parametrize(
    "kwargs",
    [
        pytest.param(dict(chunk_elements=0), id="chunk_elements zero"),
        pytest.param(dict(chunk_elements=-8), id="chunk_elements negative"),
        pytest.param(dict(seeds=[0, 1, 2]), id="fewer seeds than rewards"),
        pytest.param(dict(rewards=[0.5, 0.5, 0.5]), id="fewer rewards than seeds"),
    ],
)
def test_bad_arguments_are_rejected_even_when_the_rewards_are_equal(kwargs):
    # Equal rewards would otherwise hide the mistake behind a silent "no-op" answer.
    model = make_model()
    schema = build_parameter_schema(model)
    before = snapshot_bits(model)
    arguments = dict(seeds=SEEDS, rewards=[0.5] * 4, alpha=0.05, chunk_elements=8)
    arguments.update(kwargs)

    with pytest.raises(ValueError):
        apply_es_update_(model, schema, arguments.pop("seeds"), arguments.pop("rewards"), **arguments)

    assert same_bits(model, before)


def test_changed_is_counted_by_raw_bits_so_a_flip_of_the_sign_of_zero_counts():
    # Contract O3: bits decide, not numeric comparison (+0.0 == -0.0 as numbers).
    # alpha = 0.0 makes every update element a zero whose sign is the sign of the direction, and
    # -0.0 + (+0.0) = +0.0 while -0.0 + (-0.0) = -0.0. So exactly the elements with a positive direction
    # change their bits (from -0.0 to +0.0) although no number changes.
    class Zeros(nn.Module):
        def __init__(self):
            super().__init__()
            self.w = nn.Parameter(torch.full((1000,), -0.0, dtype=torch.float16))

    model = Zeros()
    schema = build_parameter_schema(model)
    assert (model.w.detach().view(torch.int16) == -32768).all()  # premise: all are -0.0

    report = apply_es_update_(model, schema, [0, 1], [0.0, 1.0], alpha=0.0, chunk_elements=64)

    flipped = int((model.w.detach().view(torch.int16) != -32768).sum())
    assert 0 < flipped < 1000  # premise: the data has both signs of direction
    assert report.changed == flipped
    assert bool((model.w.detach() == 0).all())  # as numbers nothing changed


def test_a_model_that_does_not_match_the_schema_is_rejected_and_untouched():
    schema = build_parameter_schema(make_model())
    other = make_model()
    other.extra = nn.Parameter(torch.zeros(2, dtype=torch.float16))
    before = snapshot_bits(other)

    with pytest.raises(SchemaMismatchError):
        apply_es_update_(other, schema, SEEDS, REWARDS, alpha=0.05)

    assert same_bits(other, before)


@pytest.mark.parametrize("bad_last, error", [("non_contiguous", ValueError), ("float32", TypeError)])
def test_a_bad_last_tensor_is_found_before_the_first_tensor_is_changed(bad_last, error):
    model = make_model(bad_last=bad_last)
    schema = build_parameter_schema(model)
    assert schema.entries[-1].canonical_name == "tail.w"  # guards the premise of this test
    before = snapshot_bits(model)

    with pytest.raises(error):
        apply_es_update_(model, schema, SEEDS, REWARDS, alpha=0.05, chunk_elements=8)

    assert same_bits(model, before)


def test_the_update_can_be_rolled_back_from_a_snapshot():
    model = make_model()
    schema = build_parameter_schema(model)
    before = snapshot_bits(model)
    snapshot = take_snapshot(model, schema)

    apply_es_update_(model, schema, SEEDS, REWARDS, alpha=0.05, chunk_elements=8)
    assert not same_bits(model, before)

    restore_from_snapshot_(model, schema, snapshot)
    assert same_bits(model, before)


# ---------------------------------------------------------------------------
# the real model
#   HETEROES_QWEN_PINNED_PATH=<snapshot dir of Qwen2.5-0.5B-Instruct @ 7ae55760...>
# ---------------------------------------------------------------------------

PINNED_PATH = os.environ.get("HETEROES_QWEN_PINNED_PATH")


def digest(model, schema):
    h = hashlib.sha256()
    for tensor in resolve_tensors(model, schema):
        h.update(tensor.detach().reshape(-1).view(torch.int16).cpu().numpy().tobytes())
    return h.hexdigest()


@pytest.mark.skipif(PINNED_PATH is None, reason="set HETEROES_QWEN_PINNED_PATH to run the real-model check")
@pytest.mark.skipif("cuda" not in DEVICES, reason="compares CPU with GPU")
def test_qwen_update_is_identical_on_cpu_and_gpu_and_can_be_rolled_back():
    from transformers import AutoModelForCausalLM

    cpu_model = AutoModelForCausalLM.from_pretrained(PINNED_PATH, dtype=torch.float16)
    schema = build_parameter_schema(cpu_model)
    gpu_model = copy.deepcopy(cpu_model).to("cuda")
    original = digest(cpu_model, schema)
    snapshot = take_snapshot(gpu_model, schema)
    seeds, rewards = [0, 1, 2, 3], [0.1, 0.4, 0.2, 0.3]

    report_cpu = apply_es_update_(cpu_model, schema, seeds, rewards, alpha=1e-3)
    torch.cuda.synchronize()
    torch.cuda.reset_peak_memory_stats()
    baseline = torch.cuda.memory_allocated()
    report_gpu = apply_es_update_(gpu_model, schema, seeds, rewards, alpha=1e-3)

    assert torch.cuda.max_memory_allocated() - baseline < 256 * 2**20  # no full-size temporaries
    assert digest(cpu_model, schema) != original
    assert digest(cpu_model, schema) == digest(gpu_model, schema)
    assert report_cpu.changed == report_gpu.changed > 0
    assert np.isfinite(report_cpu.applied_l2) and report_cpu.applied_l2 > 0

    restore_from_snapshot_(gpu_model, schema, snapshot)
    assert digest(gpu_model, schema) == original
    assert diff_from_snapshot(gpu_model, schema, snapshot) == []
