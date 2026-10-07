"""
The weights file: the model's raw FP16 bits, tensor after tensor in canonical (schema) order, nothing else.

That is also exactly what `model_weights_sha256` hashes, so the SHA-256 of the file IS the identity of the model version
(the `parent_weights_sha256` of a candidate), and a worker that downloads the file can check it before it touches its model.
These tests build the expected bytes by hand with NumPy, in the order of `model.named_parameters()` (a tied tensor once).
"""
import hashlib

import numpy as np
import pytest
import torch
import torch.nn as nn

from heteroes.eval.candidate import model_weights_sha256
from heteroes.model.schema import SchemaMismatchError, build_parameter_schema
from heteroes.model.weights_io import WeightsFileError, load_weights_, publish_weights, sha256_of_file, write_weights


class HalfToy(nn.Module):
    """FP16 with a tied tensor first, like Qwen in miniature: embed.weight (= head.weight), fc.weight, fc.bias."""

    def __init__(self, seed):
        super().__init__()
        torch.manual_seed(seed)
        self.embed = nn.Embedding(10, 4)
        self.head = nn.Linear(4, 10, bias=False)
        self.head.weight = self.embed.weight
        self.fc = nn.Linear(4, 4)
        self.half()


def expected_bytes(model):
    return b"".join(p.detach().cpu().numpy().tobytes() for _, p in model.named_parameters())


def bits(model):
    return [p.detach().clone().view(torch.int16) for p in model.parameters()]


@pytest.fixture
def model():
    return HalfToy(0)


@pytest.fixture
def schema(model):
    return build_parameter_schema(model)


# ---------------------------------------------------------------------------
# writing
# ---------------------------------------------------------------------------

def test_the_file_is_the_raw_bits_of_the_tensors_in_canonical_order_and_its_hash_is_the_model_hash(model, schema, tmp_path):
    path = tmp_path / "w.bin"

    sha = write_weights(model, schema, path)

    data = path.read_bytes()
    assert data == expected_bytes(model)
    assert len(data) == 2 * (40 + 16 + 4)                    # tied tensor counted once: 40 + fc 16 + bias 4 FP16 values
    assert sha == hashlib.sha256(data).hexdigest() == model_weights_sha256(model, schema) == sha256_of_file(path)


@pytest.mark.parametrize("slab", [1, 3, 7, 40, 61])
def test_the_slab_size_does_not_change_a_byte(model, schema, tmp_path, slab):
    path = tmp_path / "w.bin"

    write_weights(model, schema, path, slab_elements=slab)

    assert path.read_bytes() == expected_bytes(model)


def test_the_bits_that_float_comparison_would_miss_are_kept(schema, tmp_path):
    model = HalfToy(0)
    with torch.no_grad():
        model.fc.bias.view(torch.int16)[:] = torch.tensor([0x7E01, -32768, 0x0000, 0xFC00 - 65536], dtype=torch.int16)   # NaN payload, -0.0, +0.0, -inf
    path = tmp_path / "w.bin"

    sha = write_weights(model, build_parameter_schema(model), path)

    assert path.read_bytes() == expected_bytes(model) and sha == model_weights_sha256(model, build_parameter_schema(model))
    other = HalfToy(0)
    with torch.no_grad():
        other.fc.bias.view(torch.int16)[:] = torch.tensor([0x7E01, 0x0000, 0x0000, 0xFC00 - 65536], dtype=torch.int16)    # -0.0 became +0.0
    assert model_weights_sha256(other, build_parameter_schema(other)) != sha        # premise: the hash can tell


def test_an_existing_file_is_never_overwritten(model, schema, tmp_path):
    path = tmp_path / "w.bin"
    path.write_bytes(b"precious")

    with pytest.raises(FileExistsError):
        write_weights(model, schema, path)

    assert path.read_bytes() == b"precious"


def test_a_tensor_that_is_not_fp16_is_refused(tmp_path):
    model = HalfToy(0)
    model.fc.bias.data = model.fc.bias.data.float()
    with pytest.raises(SchemaMismatchError):
        write_weights(model, build_parameter_schema(HalfToy(0)), tmp_path / "w.bin")


# ---------------------------------------------------------------------------
# publishing: the file is named after its own hash
# ---------------------------------------------------------------------------

def test_publishing_names_the_file_after_the_hash_of_its_content(model, schema, tmp_path):
    sha = publish_weights(model, schema, tmp_path)

    assert sha == model_weights_sha256(model, schema)
    assert sorted(p.name for p in tmp_path.iterdir()) == [f"{sha}.bin"]            # no temporary file is left behind
    assert (tmp_path / f"{sha}.bin").read_bytes() == expected_bytes(model)


def test_publishing_the_same_weights_twice_is_harmless(model, schema, tmp_path):
    first = publish_weights(model, schema, tmp_path)
    second = publish_weights(model, schema, tmp_path)

    assert first == second and [p.name for p in tmp_path.iterdir()] == [f"{first}.bin"]


def test_publishing_creates_the_directory(model, schema, tmp_path):
    sha = publish_weights(model, schema, tmp_path / "a" / "b")

    assert (tmp_path / "a" / "b" / f"{sha}.bin").is_file()


# ---------------------------------------------------------------------------
# loading
# ---------------------------------------------------------------------------

def test_loading_gives_another_model_the_same_bits_and_keeps_the_tie(model, schema, tmp_path):
    sha = write_weights(model, schema, tmp_path / "w.bin")
    other = HalfToy(1)
    assert model_weights_sha256(other, build_parameter_schema(other)) != sha          # premise: it starts different

    load_weights_(other, build_parameter_schema(other), tmp_path / "w.bin", sha)

    assert all(torch.equal(a, b) for a, b in zip(bits(model), bits(other)))
    assert model_weights_sha256(other, build_parameter_schema(other)) == sha
    assert other.head.weight is other.embed.weight and other.head.weight.data_ptr() == other.embed.weight.data_ptr()


@pytest.mark.parametrize("slab", [1, 3, 7, 40])
def test_loading_in_small_slabs_gives_the_same_model(model, schema, tmp_path, slab):
    sha = write_weights(model, schema, tmp_path / "w.bin")
    other = HalfToy(1)

    load_weights_(other, build_parameter_schema(other), tmp_path / "w.bin", sha, slab_elements=slab)

    assert model_weights_sha256(other, build_parameter_schema(other)) == sha


def test_loading_keeps_nan_payloads_and_the_sign_of_zero(tmp_path):
    model = HalfToy(0)
    with torch.no_grad():
        model.fc.bias.view(torch.int16)[:] = torch.tensor([0x7E01, -32768, 0x0000, 0xFC00 - 65536], dtype=torch.int16)
    schema = build_parameter_schema(model)
    sha = write_weights(model, schema, tmp_path / "w.bin")
    other = HalfToy(1)

    load_weights_(other, build_parameter_schema(other), tmp_path / "w.bin", sha)

    assert model_weights_sha256(other, build_parameter_schema(other)) == sha
    assert other.fc.bias.detach().view(torch.int16).tolist() == [0x7E01, -32768, 0, 0xFC00 - 65536]


def test_a_file_with_the_wrong_hash_is_refused_before_the_model_is_touched(model, schema, tmp_path):
    write_weights(model, schema, tmp_path / "w.bin")
    other = HalfToy(1)
    before = bits(other)

    with pytest.raises(WeightsFileError, match="hash"):
        load_weights_(other, build_parameter_schema(other), tmp_path / "w.bin", "0" * 64)

    assert all(torch.equal(a, b) for a, b in zip(before, bits(other)))


def test_a_flipped_bit_is_refused_and_the_model_is_untouched(model, schema, tmp_path):
    sha = write_weights(model, schema, tmp_path / "w.bin")
    data = bytearray((tmp_path / "w.bin").read_bytes())
    data[17] ^= 0x01
    (tmp_path / "bad.bin").write_bytes(bytes(data))
    other = HalfToy(1)
    before = bits(other)

    with pytest.raises(WeightsFileError):
        load_weights_(other, build_parameter_schema(other), tmp_path / "bad.bin", sha)

    assert all(torch.equal(a, b) for a, b in zip(before, bits(other)))


@pytest.mark.parametrize("change", ["truncated", "longer"])
def test_a_file_of_the_wrong_size_is_refused_even_if_its_hash_is_claimed_right(model, schema, tmp_path, change):
    write_weights(model, schema, tmp_path / "w.bin")
    data = (tmp_path / "w.bin").read_bytes()
    data = data[:-2] if change == "truncated" else data + b"\x00\x00"
    (tmp_path / "bad.bin").write_bytes(data)
    claimed = hashlib.sha256(data).hexdigest()                  # the hash of what is in the file: the size is what is wrong
    other = HalfToy(1)
    before = bits(other)

    with pytest.raises(WeightsFileError, match="size"):
        load_weights_(other, build_parameter_schema(other), tmp_path / "bad.bin", claimed)

    assert all(torch.equal(a, b) for a, b in zip(before, bits(other)))


def test_a_missing_file_is_a_file_not_found(model, schema, tmp_path):
    with pytest.raises(FileNotFoundError):
        load_weights_(model, schema, tmp_path / "nope.bin", "0" * 64)


@pytest.mark.parametrize("bad", ["", "xyz", "A" * 64, "0" * 63, None, 5])
def test_the_expected_hash_must_be_64_lowercase_hex_digits(model, schema, tmp_path, bad):
    sha = write_weights(model, schema, tmp_path / "w.bin")

    with pytest.raises((TypeError, ValueError)):
        load_weights_(model, schema, tmp_path / "w.bin", bad)
    load_weights_(model, schema, tmp_path / "w.bin", sha)        # premise: the right one is accepted


def test_the_hash_of_a_file_does_not_depend_on_how_it_is_read(tmp_path):
    data = np.random.default_rng(0).bytes(300_001)
    (tmp_path / "f.bin").write_bytes(data)

    assert sha256_of_file(tmp_path / "f.bin", chunk_bytes=7) == sha256_of_file(tmp_path / "f.bin") == hashlib.sha256(data).hexdigest()


def test_a_model_with_another_layout_is_refused(model, schema, tmp_path):
    sha = write_weights(model, schema, tmp_path / "w.bin")
    small = nn.Linear(2, 2).half()

    with pytest.raises(SchemaMismatchError):
        load_weights_(small, schema, tmp_path / "w.bin", sha)


@pytest.mark.skipif(not torch.cuda.is_available(), reason="needs a GPU")
def test_a_model_on_the_gpu_is_written_and_loaded_with_the_same_bits(tmp_path):
    model = HalfToy(0).cuda()
    schema = build_parameter_schema(model)
    sha = write_weights(model, schema, tmp_path / "w.bin")
    assert (tmp_path / "w.bin").read_bytes() == expected_bytes(model)
    other = HalfToy(1).cuda()

    load_weights_(other, build_parameter_schema(other), tmp_path / "w.bin", sha)

    assert model_weights_sha256(other, build_parameter_schema(other)) == sha


def test_a_write_that_fails_halfway_leaves_no_file_behind(model, schema, tmp_path):
    path = tmp_path / "w.bin"

    with pytest.raises(ValueError):
        write_weights(model, schema, path, slab_elements=0)             # fails after the file was created

    assert not path.exists()


def test_a_file_that_shrinks_after_it_was_checked_is_noticed_while_copying(model, schema, tmp_path, monkeypatch):
    import heteroes.model.weights_io as weights_io

    sha = write_weights(model, schema, tmp_path / "w.bin")
    real = weights_io.sha256_of_file

    def checked_then_cut(path, *args, **kwargs):
        digest = real(path, *args, **kwargs)
        with open(path, "r+b") as file:
            file.truncate(10)                                          # somebody cuts the file after the hash was computed
        return digest

    monkeypatch.setattr(weights_io, "sha256_of_file", checked_then_cut)

    with pytest.raises(WeightsFileError, match="ended early"):
        load_weights_(HalfToy(1), build_parameter_schema(HalfToy(1)), tmp_path / "w.bin", sha)


# ---------------------------------------------------------------------------
# G6: publishing in two steps (write and hash once, commit after the ledger has been told), and a load that trusts a hash already checked
# ---------------------------------------------------------------------------

from heteroes.model.weights_io import prepare_publication  # noqa: E402


def test_a_prepared_publication_has_the_hash_but_no_visible_file_until_it_is_committed(model, schema, tmp_path):
    publication = prepare_publication(model, schema, tmp_path / "pub")

    assert publication.sha256 == model_weights_sha256(model, schema)
    assert list((tmp_path / "pub").glob("*.bin")) == []                      # nothing a worker could be served yet
    path = publication.commit()
    assert path == tmp_path / "pub" / f"{publication.sha256}.bin" and path.read_bytes() == expected_bytes(model)
    assert [p.name for p in (tmp_path / "pub").iterdir()] == [path.name]      # and no temporary file is left


def test_a_prepared_publication_can_be_discarded_and_leaves_nothing(model, schema, tmp_path):
    publication = prepare_publication(model, schema, tmp_path / "pub")
    publication.discard()
    assert list((tmp_path / "pub").iterdir()) == []


def test_committing_replaces_a_damaged_file_of_the_same_name_and_keeps_an_intact_one(model, schema, tmp_path):
    publication = prepare_publication(model, schema, tmp_path)
    (tmp_path / f"{publication.sha256}.bin").write_bytes(b"damaged by a crash")      # named after the hash, content is not it
    path = publication.commit()
    assert sha256_of_file(path) == publication.sha256

    again = prepare_publication(model, schema, tmp_path)
    before = path.stat().st_mtime_ns
    assert again.commit() == path and path.stat().st_mtime_ns == before               # an intact file is kept as it is
    assert [p.name for p in tmp_path.iterdir()] == [path.name]


def test_publish_weights_replaces_a_damaged_file_too(model, schema, tmp_path):
    sha = model_weights_sha256(model, schema)
    (tmp_path / f"{sha}.bin").write_bytes(b"x" * (2 * sum(p.numel() for p in model.parameters())))     # right size, wrong content
    assert publish_weights(model, schema, tmp_path) == sha
    assert sha256_of_file(tmp_path / f"{sha}.bin") == sha


def test_a_load_that_trusts_a_hash_already_checked_skips_the_hash_but_not_the_size(model, schema, tmp_path):
    other = HalfToy(7)
    path = tmp_path / "w.bin"
    sha = write_weights(other, schema, path)
    target = HalfToy(0)

    load_weights_(target, schema, path, sha, already_verified=True)
    assert model_weights_sha256(target, schema) == sha

    wrong = HalfToy(9)
    # the caller vouches for the hash: a file with other content but the right size IS loaded (that is what "already verified" means) ...
    load_weights_(wrong, schema, path, "0" * 64, already_verified=True)
    assert model_weights_sha256(wrong, schema) == sha
    # ... and the default still checks it
    with pytest.raises(WeightsFileError, match="wrong hash"):
        load_weights_(HalfToy(9), schema, path, "0" * 64)
    # the size is always checked
    path.write_bytes(path.read_bytes()[:-2])
    with pytest.raises(WeightsFileError, match="wrong size"):
        load_weights_(HalfToy(9), schema, path, sha, already_verified=True)


# ---------------------------------------------------------------------------
# G6: the published directory does not grow for ever
# ---------------------------------------------------------------------------

from heteroes.model.weights_io import prune_published  # noqa: E402


def _files(directory):
    return sorted(p.name for p in directory.iterdir())


def test_prune_keeps_only_the_named_versions_and_removes_the_other_weights_files(tmp_path):
    names = [f"{c * 64}.bin" for c in "abcd"]
    for name in names:
        (tmp_path / name).write_bytes(b"x")
    removed = prune_published(tmp_path, keep=["a" * 64, "c" * 64])
    assert _files(tmp_path) == [names[0], names[2]]
    assert sorted(removed) == [names[1], names[3]]


def test_prune_leaves_everything_that_is_not_a_published_weights_file(tmp_path):
    (tmp_path / f"{'a' * 64}.bin").write_bytes(b"x")
    (tmp_path / "notes.txt").write_text("keep me")
    (tmp_path / f".tmp-1-abc").write_bytes(b"in use by a publication")              # a temporary file may belong to a write in progress
    (tmp_path / "short.bin").write_bytes(b"x")                                      # not named after a SHA-256
    (tmp_path / "sub").mkdir()
    prune_published(tmp_path, keep=[])
    assert _files(tmp_path) == [".tmp-1-abc", "notes.txt", "short.bin", "sub"]


def test_prune_of_a_directory_that_does_not_exist_is_a_no_op(tmp_path):
    assert prune_published(tmp_path / "nothing", keep=["a" * 64]) == []


def test_prune_refuses_a_keep_list_that_is_not_hashes(tmp_path):
    with pytest.raises(ValueError):
        prune_published(tmp_path, keep=["not a hash"])
