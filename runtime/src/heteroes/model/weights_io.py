"""
The weights of a model as one file: the raw FP16 bits of every tensor, in canonical (schema) order, nothing else.

This is exactly what `heteroes.eval.candidate.model_weights_sha256` hashes, so the SHA-256 of the file is the identity of
that version of the model (the `parent_weights_sha256` of a candidate) and the file is named after it: `<sha256>.bin`. A
worker that downloads a file can check it before it touches its model (full synchronization, the baseline of MASTER's C4).
The bits are copied, never converted: NaN payloads and the sign of zero survive. A model is written and read in slabs, so a
6 GB card (and the RAM next to it) never holds a second copy.
"""
import hashlib
import os
import re
import uuid
from pathlib import Path

import torch

from heteroes.es.checks import _check_param
from heteroes.model.schema import ParameterSchema, resolve_tensors

DEFAULT_SLAB_ELEMENTS = 2**23          # 16 MiB of FP16 per slab
_HEX64 = re.compile(r"[0-9a-f]{64}")


class WeightsFileError(Exception):
    """The file is not the weights it should be (wrong size or wrong hash). The model was not touched."""


def _tensors(model, schema: ParameterSchema) -> list[torch.Tensor]:
    tensors = resolve_tensors(model, schema)
    for tensor in tensors:
        _check_param(tensor)
    return tensors


def sha256_of_file(path, chunk_bytes: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as file:
        while chunk := file.read(chunk_bytes):
            digest.update(chunk)
    return digest.hexdigest()


def write_weights(model, schema: ParameterSchema, path, slab_elements: int = DEFAULT_SLAB_ELEMENTS) -> str:
    """Write the weights to `path`, which must not exist (FileExistsError), and return their SHA-256."""
    tensors = _tensors(model, schema)
    digest = hashlib.sha256()
    path = Path(path)
    with open(path, "xb") as file:
        try:
            with torch.no_grad():
                for tensor in tensors:
                    flat = tensor.detach().reshape(-1)
                    for start in range(0, flat.numel(), slab_elements):
                        data = flat[start:start + slab_elements].view(torch.int16).cpu().numpy()    # a buffer: no extra copy to bytes
                        digest.update(data)
                        file.write(data)
        except BaseException:
            file.close()
            path.unlink()                      # never leave half a file that looks like the weights
            raise
    return digest.hexdigest()


def _fsync_directory(directory) -> None:
    try:
        fd = os.open(directory, os.O_RDONLY)
    except OSError:                       # a platform that cannot open a directory: the rename is still atomic
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


class Publication:
    """
    Weights written to a temporary file, hashed while they were written, and not yet visible under their name. `commit()` makes them
    visible (atomically); `discard()` forgets them. Writing and hashing happen once, here, so that the caller can know the hash
    (and record it) BEFORE the file becomes available to the workers.

    The file is not fsynced: a file damaged by a power cut is caught by the hash check of whoever reads it (`load_weights_`,
    `Coordinator.recover`, and `commit` itself for a file that is already there) and is then recomputed or fetched again.
    """

    def __init__(self, directory: Path, temporary: Path, sha256: str):
        self.directory, self.temporary, self.sha256 = directory, temporary, sha256

    @property
    def path(self) -> Path:
        return self.directory / f"{self.sha256}.bin"

    def commit(self) -> Path:
        final = self.path
        # A file that is already there is kept only if it really is these weights: a file damaged by a crash or a full disk and
        # still named after the hash would otherwise be served to the workers for ever.
        if final.exists() and final.stat().st_size == self.temporary.stat().st_size and sha256_of_file(final) == self.sha256:
            self.temporary.unlink()
        else:
            os.replace(self.temporary, final)
            _fsync_directory(self.directory)
        return final

    def discard(self) -> None:
        self.temporary.unlink(missing_ok=True)


def prepare_publication(model, schema: ParameterSchema, directory, slab_elements: int = DEFAULT_SLAB_ELEMENTS) -> Publication:
    """Write the weights to a temporary file in `directory` (created if needed) and return the `Publication` (hash known, not yet visible)."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    temporary = directory / f".tmp-{os.getpid()}-{uuid.uuid4().hex}"
    sha = write_weights(model, schema, temporary, slab_elements)
    return Publication(directory, temporary, sha)


def publish_weights(model, schema: ParameterSchema, directory, slab_elements: int = DEFAULT_SLAB_ELEMENTS) -> str:
    """Write the weights as `<directory>/<sha256>.bin` (atomically) and return the hash; the same weights twice are one file."""
    publication = prepare_publication(model, schema, directory, slab_elements)
    publication.commit()
    return publication.sha256


def load_weights_(model, schema: ParameterSchema, path, expected_sha256: str, slab_elements: int = DEFAULT_SLAB_ELEMENTS,
                  already_verified: bool = False) -> None:
    """
    Copy the weights in `path` into the model, in place. The size and the SHA-256 of the whole file are checked FIRST: a
    file that is not `expected_sha256` raises WeightsFileError and the model is not touched. (A failure of the disk while
    copying would leave the model half loaded: the caller must then treat the model as unreliable.)

    `already_verified=True` skips the hash of the file (about a second per GB, and a second read of it): for a caller that has just
    checked it, such as a download that hashed every byte as it arrived. The size is always checked.
    """
    if not isinstance(expected_sha256, str):
        raise TypeError(f"expected_sha256 must be a string, got {type(expected_sha256).__name__}")
    if not _HEX64.fullmatch(expected_sha256):
        raise ValueError(f"expected_sha256 must be 64 lowercase hex digits, got {expected_sha256!r}")
    tensors = _tensors(model, schema)
    expected_size = 2 * sum(tensor.numel() for tensor in tensors)
    path = Path(path)
    size = path.stat().st_size
    if size != expected_size:
        raise WeightsFileError(f"{path.name} has {size} bytes, the model needs {expected_size}: wrong size")
    if not already_verified:
        actual = sha256_of_file(path)
        if actual != expected_sha256:
            raise WeightsFileError(f"{path.name} has the hash {actual}, expected {expected_sha256}: wrong hash")

    with open(path, "rb") as file, torch.no_grad():
        for tensor in tensors:
            flat = tensor.reshape(-1)
            for start in range(0, flat.numel(), slab_elements):
                count = min(slab_elements, flat.numel() - start)
                buffer = bytearray(2 * count)
                if file.readinto(buffer) != 2 * count:
                    raise WeightsFileError(f"{path.name} ended early")        # the file changed after it was checked
                flat[start:start + count].copy_(torch.frombuffer(buffer, dtype=torch.int16).view(torch.float16))


def tensors_match_file(tensors, path, slab_elements: int = DEFAULT_SLAB_ELEMENTS) -> bool:
    """
    Are these tensors (canonical order, FP16) bit for bit the weights file at `path`? Compared, not hashed: at the speed of memory, so a
    worker that has just checked the hash of a downloaded file can check that its model IS that file without a second hash.
    A file of another size is simply "no".
    """
    import numpy as np

    path = Path(path)
    if path.stat().st_size != 2 * sum(tensor.numel() for tensor in tensors):
        return False
    with open(path, "rb") as file:
        for tensor in tensors:
            flat = tensor.detach().reshape(-1).view(torch.int16).cpu().numpy()
            for start in range(0, flat.size, slab_elements):
                part = flat[start:start + slab_elements]
                expected = np.frombuffer(file.read(2 * part.size), dtype=np.int16)
                if expected.size != part.size or not np.array_equal(expected, part):
                    return False
    return True


def prune_published(directory, keep) -> list[str]:
    """
    Delete the published weights files (`<64 hex digits>.bin`) of `directory` whose hash is not in `keep`; return their names.
    Nothing else is touched: other files, directories and the temporary files of a write in progress stay. A weights file is about
    1 GB, one per generation, and the coordinator used to keep them all.
    """
    keep = list(keep)
    for sha256 in keep:
        if not isinstance(sha256, str) or not _HEX64.fullmatch(sha256):
            raise ValueError(f"keep must hold 64 lowercase hex digits, got {sha256!r}")
    directory = Path(directory)
    if not directory.is_dir():
        return []
    removed = []
    for path in sorted(directory.iterdir()):
        if path.is_file() and re.fullmatch(r"[0-9a-f]{64}\.bin", path.name) and path.name[:-4] not in keep:
            path.unlink()
            removed.append(path.name)
    return removed
