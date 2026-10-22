"""V2 golden vectors from the independent raw-PCG/searchsorted oracle.

Initial vectors are local regression guards until reproduced on the acceptance
machines; the evidence folder records that distinction.
"""

import hashlib

from heteroes.canonical import canonical_json_hash
from heteroes.noise.contracts import DEFAULT_CHUNK_ELEMENTS, ENGINE_V2, EXPECTED_V2_NOISE_FINGERPRINT, ChunkNoiseAddress
from heteroes.noise.engine_v2 import generate_chunk_noise, table_selftest
from heteroes.noise.selftest import SELFTEST_SCHEMA_HASH, SELFTEST_SEED

GOLDEN_CHUNKS_V2 = (
    (0, 0, 262144, "ca251beabc189cd102b1ae188090b8f30478b9d350fe088565e00c0a03f002a9"),
    (0, 519, 81920, "4a497892d872836ec7dc77e9d8030e1079de749c04e804cf55edb2a51c6b7c66"),
    (1, 0, 262144, "38dfcc538b47d1ad431b5ab695ed2d7fcdfcfed4e9d21f68c2791247f21fbea0"),
    (2, 0, 896, "80894690efa77bd1f40b0cc0cba5769adf7851247b74aa0b129e92ce5d6b5508"),
    (289, 0, 896, "767df8b1bce4365f887162fe0b56250f2384b5ef326422a297a1f1be0783c351"),
)


def compute_noise_fingerprint() -> str:
    if not table_selftest():
        raise ValueError("V2 noise threshold table hash mismatch")
    rows = []
    for parameter, chunk, n, _ in GOLDEN_CHUNKS_V2:
        address = ChunkNoiseAddress(SELFTEST_SEED, SELFTEST_SCHEMA_HASH, parameter, chunk, DEFAULT_CHUNK_ELEMENTS)
        rows.append([parameter, chunk, n, hashlib.sha256(generate_chunk_noise(address, n).tobytes()).hexdigest()])
    return canonical_json_hash(
        {
            "engine_version": ENGINE_V2,
            "chunk_elements": DEFAULT_CHUNK_ELEMENTS,
            "seed": SELFTEST_SEED,
            "schema_hash": SELFTEST_SCHEMA_HASH,
            "chunks": rows,
        }
    )


def noise_selftest() -> bool:
    return compute_noise_fingerprint() == EXPECTED_V2_NOISE_FINGERPRINT
