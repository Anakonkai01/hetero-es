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
                        data = flat[start:start + slab_elements].view(torch.int16).cpu().numpy().tobytes()
                        digest.update(data)
                        file.write(data)
        except BaseException:
            file.close()
            path.unlink()                      # never leave half a file that looks like the weights
            raise
    return digest.hexdigest()


def publish_weights(model, schema: ParameterSchema, directory, slab_elements: int = DEFAULT_SLAB_ELEMENTS) -> str:
    """Write the weights as `<directory>/<sha256>.bin` (atomically) and return the hash; the same weights twice are one file."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    temporary = directory / f".tmp-{os.getpid()}-{uuid.uuid4().hex}"
    sha = write_weights(model, schema, temporary, slab_elements)
    final = directory / f"{sha}.bin"
    if final.exists():
        temporary.unlink()
    else:
        os.replace(temporary, final)
    return sha


def load_weights_(model, schema: ParameterSchema, path, expected_sha256: str, slab_elements: int = DEFAULT_SLAB_ELEMENTS) -> None:
    """
    Copy the weights in `path` into the model, in place. The size and the SHA-256 of the whole file are checked FIRST: a
    file that is not `expected_sha256` raises WeightsFileError and the model is not touched. (A failure of the disk while
    copying would leave the model half loaded: the caller must then treat the model as unreliable.)
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
