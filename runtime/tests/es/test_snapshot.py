import hashlib
import os

import pytest
import torch
import torch.nn as nn

from heteroes.es.perturb import perturb_model_
from heteroes.es.snapshot import RestoreError, diff_from_snapshot, restore_from_snapshot_, take_snapshot
from heteroes.model.schema import SchemaMismatchError, build_parameter_schema, resolve_tensors

DEVICES = ["cpu"] + (["cuda"] if torch.cuda.is_available() else [])


class HalfToy(nn.Module):
    # FP16 model in miniature. Parameters in canonical order:
    #   embed.weight (40 elements, tied with head.weight), fc.weight (16), fc.bias (4)
    # plus, optionally, a bad tensor that comes LAST (inside a child module, because PyTorch lists a
    # module's own parameters before its children's).
    def __init__(self, bad_last=None, fc_out=4):
        super().__init__()
        self.embed = nn.Embedding(10, 4)
        self.head = nn.Linear(4, 10, bias=False)
        self.head.weight = self.embed.weight
        self.fc = nn.Linear(4, fc_out)
        self.half()
        if bad_last is not None:
            self.tail = nn.Module()
            if bad_last == "non_contiguous":
                self.tail.w = nn.Parameter(torch.zeros(4, 3, dtype=torch.float16).t())
            elif bad_last == "float32":
                self.tail.w = nn.Parameter(torch.zeros(3, dtype=torch.float32))


def make_model(bad_last=None, device="cpu", fc_out=4):
    torch.manual_seed(0)
    model = HalfToy(bad_last, fc_out)
    assert model.head.weight is model.embed.weight  # the tie survived
    return model.to(device)


def bits_of(model):
    return [p.detach().cpu().reshape(-1).view(torch.int16).clone() for p in model.parameters()]


def same_bits(model, reference):
    return all(torch.equal(a, b) for a, b in zip(bits_of(model), reference))


def flip_lowest_bit(tensor, k):
    flat = tensor.detach().view(-1).view(torch.int16)  # shares memory with the tensor
    flat[k] = flat[k] ^ 1


# ---------------------------------------------------------------------------
# take_snapshot
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("device", DEVICES)
def test_snapshot_is_an_independent_fp16_copy_on_the_cpu(device):
    model = make_model(device=device)
    schema = build_parameter_schema(model)
    reference = bits_of(model)

    snapshot = take_snapshot(model, schema)
    for tensor in resolve_tensors(model, schema):
        tensor.data.zero_()  # damage the model after the snapshot

    assert snapshot.schema_hash == schema.hash
    assert all(t.device.type == "cpu" and t.dtype == torch.float16 for t in snapshot.tensors)
    assert all(torch.equal(t.reshape(-1).view(torch.int16), r) for t, r in zip(snapshot.tensors, reference))


def test_a_tied_tensor_is_stored_once():
    model = make_model()
    schema = build_parameter_schema(model)

    snapshot = take_snapshot(model, schema)

    assert len(snapshot.tensors) == len(schema.entries) == 3


def test_snapshot_rejects_a_model_that_does_not_match_the_schema():
    schema = build_parameter_schema(make_model())

    with pytest.raises(SchemaMismatchError):
        take_snapshot(make_model(fc_out=5), schema)


@pytest.mark.parametrize("bad_last, error", [("non_contiguous", ValueError), ("float32", TypeError)])
def test_snapshot_rejects_tensors_that_restore_could_not_handle(bad_last, error):
    model = make_model(bad_last=bad_last)

    with pytest.raises(error):
        take_snapshot(model, build_parameter_schema(model))


# ---------------------------------------------------------------------------
# the point of it all: perturb, then restore, is bitwise exact
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("device", DEVICES)
def test_perturb_then_restore_gives_back_exactly_the_original_bits(device):
    model = make_model(device=device)
    schema = build_parameter_schema(model)
    reference = bits_of(model)
    snapshot = take_snapshot(model, schema)

    perturb_model_(model, schema, candidate_seed=3, sigma=5e-2, chunk_elements=8)
    assert not same_bits(model, reference)  # the perturbation really changed something

    restore_from_snapshot_(model, schema, snapshot)

    assert same_bits(model, reference)
    assert model.head.weight is model.embed.weight


def test_many_candidates_in_a_row_always_return_to_the_same_bits():
    model = make_model()
    schema = build_parameter_schema(model)
    reference = bits_of(model)
    snapshot = take_snapshot(model, schema)

    for seed in range(5):
        perturb_model_(model, schema, candidate_seed=seed, sigma=5e-2, chunk_elements=8)
        restore_from_snapshot_(model, schema, snapshot)
        assert same_bits(model, reference)


def test_subtracting_the_noise_does_not_restore_bitwise():
    # Why snapshots exist (decision O3): arithmetic undo is not exact in floating point.
    model = make_model()
    schema = build_parameter_schema(model)
    reference = bits_of(model)

    perturb_model_(model, schema, candidate_seed=3, sigma=5e-2, chunk_elements=8)
    perturb_model_(model, schema, candidate_seed=3, sigma=-5e-2, chunk_elements=8)

    assert not same_bits(model, reference)


def test_restore_writes_in_place_and_keeps_the_storage():
    model = make_model()
    schema = build_parameter_schema(model)
    pointers = [t.data_ptr() for t in resolve_tensors(model, schema)]
    snapshot = take_snapshot(model, schema)
    perturb_model_(model, schema, candidate_seed=3, sigma=5e-2, chunk_elements=8)

    restore_from_snapshot_(model, schema, snapshot)

    assert [t.data_ptr() for t in resolve_tensors(model, schema)] == pointers


def test_the_same_snapshot_can_be_restored_again_and_again():
    model = make_model()
    schema = build_parameter_schema(model)
    reference = bits_of(model)
    snapshot = take_snapshot(model, schema)

    for _ in range(3):
        perturb_model_(model, schema, candidate_seed=1, sigma=5e-2, chunk_elements=8)
        restore_from_snapshot_(model, schema, snapshot)

    assert same_bits(model, reference)
    assert all(torch.equal(t.reshape(-1).view(torch.int16), r) for t, r in zip(snapshot.tensors, reference))


# ---------------------------------------------------------------------------
# diff_from_snapshot: the bitwise oracle (decision O3)
# ---------------------------------------------------------------------------

def test_diff_is_empty_when_nothing_changed():
    model = make_model()
    schema = build_parameter_schema(model)

    assert diff_from_snapshot(model, schema, take_snapshot(model, schema)) == []


def test_diff_names_the_changed_tensors_in_canonical_order():
    model = make_model()
    schema = build_parameter_schema(model)
    snapshot = take_snapshot(model, schema)
    tensors = resolve_tensors(model, schema)
    flip_lowest_bit(tensors[2], 0)  # fc.bias
    flip_lowest_bit(tensors[0], 5)  # embed.weight

    assert diff_from_snapshot(model, schema, snapshot) == ["embed.weight", "fc.bias"]


@pytest.mark.parametrize("slab_elements", [1, 3, 4, 7, 10_000])
@pytest.mark.parametrize("position", [0, 3, 4, 6, 7, 39])
def test_diff_finds_a_single_flipped_bit_wherever_it_is_and_whatever_the_slab_size(slab_elements, position):
    # embed.weight has 40 elements: positions sit on, before and after slab boundaries,
    # and 39 is the very last element.
    model = make_model()
    schema = build_parameter_schema(model)
    snapshot = take_snapshot(model, schema)
    embed = resolve_tensors(model, schema)[0]

    flip_lowest_bit(embed, position)
    assert diff_from_snapshot(model, schema, snapshot, slab_elements=slab_elements) == ["embed.weight"]

    flip_lowest_bit(embed, position)  # flip it back
    assert diff_from_snapshot(model, schema, snapshot, slab_elements=slab_elements) == []


def test_diff_names_a_tensor_once_even_if_several_slabs_of_it_differ():
    model = make_model()
    schema = build_parameter_schema(model)
    snapshot = take_snapshot(model, schema)
    embed = resolve_tensors(model, schema)[0]
    flip_lowest_bit(embed, 0)   # first slab
    flip_lowest_bit(embed, 39)  # last slab

    assert diff_from_snapshot(model, schema, snapshot, slab_elements=4) == ["embed.weight"]


def test_diff_sees_a_nan_where_the_snapshot_has_a_number():
    # A numeric comparison cannot be trusted with NaN, a bit comparison can.
    model = make_model()
    schema = build_parameter_schema(model)
    snapshot = take_snapshot(model, schema)

    with torch.no_grad():
        resolve_tensors(model, schema)[1].view(-1)[2] = float("nan")

    assert diff_from_snapshot(model, schema, snapshot) == ["fc.weight"]


def test_diff_does_not_complain_when_the_snapshot_itself_holds_the_same_nan():
    # NaN != NaN as numbers, but the bits are identical, so the oracle must say "no difference".
    model = make_model()
    schema = build_parameter_schema(model)
    with torch.no_grad():
        resolve_tensors(model, schema)[1].view(-1)[2] = float("nan")
    snapshot = take_snapshot(model, schema)

    assert diff_from_snapshot(model, schema, snapshot) == []


def test_diff_sees_the_sign_of_zero():
    model = make_model()
    schema = build_parameter_schema(model)
    bias = resolve_tensors(model, schema)[2]
    with torch.no_grad():
        bias[1] = 0.0
    snapshot = take_snapshot(model, schema)

    with torch.no_grad():
        bias[1] = -0.0
    assert bias.detach().view(torch.int16)[1].item() == -32768  # premise: really negative zero
    assert torch.equal(bias.detach(), snapshot.tensors[2])      # as numbers they are "equal"

    assert diff_from_snapshot(model, schema, snapshot) == ["fc.bias"]


def test_diff_rejects_a_model_that_does_not_match_the_schema():
    schema = build_parameter_schema(make_model())
    snapshot = take_snapshot(make_model(), schema)

    with pytest.raises(SchemaMismatchError):
        diff_from_snapshot(make_model(fc_out=5), schema, snapshot)


@pytest.mark.parametrize("bad_slab", [0, -1, -4])
def test_diff_rejects_a_slab_size_that_would_make_it_compare_nothing(bad_slab):
    # A negative slab size makes range() empty: without a check the oracle would answer
    # "identical" for a model that is NOT identical. An oracle must fail loudly, never reassure.
    model = make_model()
    schema = build_parameter_schema(model)
    snapshot = take_snapshot(model, schema)
    flip_lowest_bit(resolve_tensors(model, schema)[0], 0)

    with pytest.raises(ValueError, match="slab"):
        diff_from_snapshot(model, schema, snapshot, slab_elements=bad_slab)


@pytest.mark.parametrize("bad_slab", [0, -1])
def test_restore_rejects_a_bad_slab_size_before_touching_the_model(bad_slab):
    model = make_model()
    schema = build_parameter_schema(model)
    snapshot = take_snapshot(model, schema)
    perturb_model_(model, schema, candidate_seed=3, sigma=5e-2, chunk_elements=8)
    perturbed = bits_of(model)

    with pytest.raises(ValueError, match="slab"):
        restore_from_snapshot_(model, schema, snapshot, slab_elements=bad_slab)

    assert same_bits(model, perturbed)


def test_diff_rejects_a_snapshot_taken_for_another_schema():
    model = make_model()
    schema = build_parameter_schema(model)
    other = make_model(fc_out=5)
    foreign_snapshot = take_snapshot(other, build_parameter_schema(other))

    with pytest.raises(SchemaMismatchError):
        diff_from_snapshot(model, schema, foreign_snapshot)


@pytest.mark.skipif("cuda" not in DEVICES, reason="needs a CUDA GPU")
def test_verifying_does_not_copy_a_whole_tensor_to_the_gpu():
    # The 6 GB worker cannot afford a full-size temporary copy of the big embedding.
    class Big(nn.Module):
        def __init__(self):
            super().__init__()
            self.w = nn.Parameter(torch.zeros(2**26, dtype=torch.float16))  # 128 MiB

    model = Big().to("cuda")
    schema = build_parameter_schema(model)
    snapshot = take_snapshot(model, schema)
    torch.cuda.synchronize()
    torch.cuda.reset_peak_memory_stats()
    baseline = torch.cuda.memory_allocated()

    assert diff_from_snapshot(model, schema, snapshot, slab_elements=2**20) == []

    extra = torch.cuda.max_memory_allocated() - baseline
    assert extra < 16 * 2**20  # a few slabs, nowhere near 128 MiB


# ---------------------------------------------------------------------------
# restore_from_snapshot_: validation and failure
# ---------------------------------------------------------------------------

def test_restore_fixes_every_damaged_tensor_not_only_the_perturbed_ones():
    model = make_model()
    schema = build_parameter_schema(model)
    reference = bits_of(model)
    snapshot = take_snapshot(model, schema)
    tensors = resolve_tensors(model, schema)
    flip_lowest_bit(tensors[1], 7)
    with torch.no_grad():
        tensors[2].zero_()

    restore_from_snapshot_(model, schema, snapshot)

    assert same_bits(model, reference)


def test_restore_rejects_a_snapshot_taken_for_another_schema_and_touches_nothing():
    model = make_model()
    schema = build_parameter_schema(model)
    other = make_model(fc_out=5)
    foreign_snapshot = take_snapshot(other, build_parameter_schema(other))
    perturb_model_(model, schema, candidate_seed=3, sigma=5e-2, chunk_elements=8)
    perturbed = bits_of(model)

    with pytest.raises(SchemaMismatchError):
        restore_from_snapshot_(model, schema, foreign_snapshot)

    assert same_bits(model, perturbed)


def test_restore_rejects_a_model_that_does_not_match_the_schema():
    schema = build_parameter_schema(make_model())
    snapshot = take_snapshot(make_model(), schema)

    with pytest.raises(SchemaMismatchError):
        restore_from_snapshot_(make_model(fc_out=5), schema, snapshot)


def test_restore_raises_when_the_copy_silently_fails(monkeypatch):
    # If the write does not really happen, restore must notice and say so (the worker is then
    # unusable, contract section 6). restore_from_snapshot_ must write with Tensor.copy_ (in place).
    model = make_model()
    schema = build_parameter_schema(model)
    snapshot = take_snapshot(model, schema)
    perturb_model_(model, schema, candidate_seed=3, sigma=5e-2, chunk_elements=8)

    monkeypatch.setattr(torch.Tensor, "copy_", lambda self, *args, **kwargs: self)

    with pytest.raises(RestoreError) as info:
        restore_from_snapshot_(model, schema, snapshot)

    assert "embed.weight" in str(info.value)


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
def test_qwen_perturb_then_restore_is_bitwise_exact():
    from transformers import AutoModelForCausalLM

    model = AutoModelForCausalLM.from_pretrained(PINNED_PATH, dtype=torch.float16)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model.to(device)
    schema = build_parameter_schema(model)
    original = digest(model, schema)
    snapshot = take_snapshot(model, schema)

    perturb_model_(model, schema, candidate_seed=0, sigma=1e-3)
    assert digest(model, schema) != original

    if device == "cuda":
        torch.cuda.synchronize()
        torch.cuda.reset_peak_memory_stats()
        baseline = torch.cuda.memory_allocated()
    restore_from_snapshot_(model, schema, snapshot)

    assert digest(model, schema) == original
    assert diff_from_snapshot(model, schema, snapshot) == []
    if device == "cuda":
        assert torch.cuda.max_memory_allocated() - baseline < 256 * 2**20  # no full-size temporaries
