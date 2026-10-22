"""Versioned integer quantile mapping to FP16; no host libm dependency.

For a uint32 word w, sign=w>>31, u=w&0x7fffffff. Magnitude bits are the
number of thresholds <= u. This is a finite, quantized Gaussian FP16 law,
not an exact continuous Gaussian. See numerical-contract.md, CPU v2.
"""

import hashlib

import numpy as np

from heteroes.noise._thresholds_v2 import TABLE_SHA256, THRESHOLDS
from heteroes.noise.contracts import ENGINE_V2, EXPECTED_V2_TABLE_SHA256, ChunkNoiseAddress

_TABLE = np.array(THRESHOLDS, dtype="<u4")
_TABLE.setflags(write=False)
# Sentinel handles the top bucket without an out-of-bounds threshold read.
_SENTINEL_TABLE = np.append(_TABLE, np.uint32(0xFFFFFFFF))
_STARTS = np.arange(65536, dtype=np.uint32) << np.uint32(15)
_LO = np.searchsorted(_TABLE, _STARTS, side="right")
_HI = np.searchsorted(_TABLE, _STARTS + np.uint32(32767), side="right")
_BUCKETS = (_LO | ((_HI - _LO >= 2) << 15)).astype(np.uint16)
_BUCKETS.setflags(write=False)
BLOCK_ELEMENTS = 131072


def table_selftest() -> bool:
    return (
        TABLE_SHA256 == EXPECTED_V2_TABLE_SHA256
        and hashlib.sha256(_TABLE.tobytes()).hexdigest() == EXPECTED_V2_TABLE_SHA256
    )


def derive_chunk_seed(address: ChunkNoiseAddress) -> int:
    material = (
        f"{ENGINE_V2}|candidate_seed={address.candidate_seed}|schema={address.schema_hash}"
        f"|param={address.parameter_index}|chunk={address.chunk_index}|chunk_elements={address.chunk_elements}"
    )
    return int.from_bytes(hashlib.sha256(material.encode("utf-8")).digest()[:16], "little")


def transform_words(words: np.ndarray) -> np.ndarray:
    """Pure integer mapping; block size and scheduling never affect output bits."""
    words = np.asarray(words, dtype="<u4")
    out = np.empty(words.size, dtype="<u2")
    for start in range(0, words.size, BLOCK_ELEMENTS):
        raw = words[start : start + BLOCK_ELEMENTS]
        u = raw & np.uint32(0x7FFFFFFF)
        bucket = _BUCKETS[u >> np.uint32(15)]
        lo = bucket & np.uint16(0x7FFF)
        magnitude = lo + (u >= _SENTINEL_TABLE[lo])
        multi = bucket >= np.uint16(0x8000)
        if multi.any():
            magnitude[multi] = np.searchsorted(_TABLE, u[multi], side="right").astype(np.uint16)
        out[start : start + raw.size] = magnitude | ((raw >> np.uint32(31)).astype(np.uint16) << np.uint16(15))
    return out.view("<f2")


def generate_chunk_noise(address: ChunkNoiseAddress, n: int) -> np.ndarray:
    if not 1 <= n <= address.chunk_elements:
        raise ValueError("n must be in range 1 <= n <= chunk_elements")
    raw = np.random.PCG64(derive_chunk_seed(address)).random_raw((n + 1) // 2)
    return transform_words(raw.astype("<u8", copy=False).view("<u4")[:n])
