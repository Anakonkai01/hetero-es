import hashlib

from heteroes.canonical import canonical_json_hash
from heteroes.noise.contracts import DEFAULT_CHUNK_ELEMENTS, ENGINE_VERSION, ChunkNoiseAddress
from heteroes.noise.engine import generate_chunk_noise

# A fixed address, used only by this self-test. The schema hash is the production hash of the Qwen2.5-0.5B layout,
# the one the digests below were recorded with; it does not have to match the schema of the model in use.
SELFTEST_SCHEMA_HASH = "0b21250e331398a266785dc473da3a8b8f5e8f98fa15e9044637d742eb7845ec"
SELFTEST_SEED = 0

# (parameter index, chunk index, number of elements, SHA-256 of the FP16 bytes) of five real chunks.
# Recorded on 2026-10-03 and reproduced on the 5070 Ti, the 1660 SUPER, Colab and Kaggle
# (artifacts/regression/2026-10-03-o2-perturbation/).
GOLDEN_CHUNKS = (
    (0, 0, 262144, "ebe2addd4ba90dfaebfad1582712b1660bd271f99e637c0e554caacf5fbcf87c"),
    (0, 519, 81920, "0d1468c0d034367ccd85e3ac80b5d94d7bf37aaf3a11edb718a35cfc5195466c"),
    (1, 0, 262144, "cd47f0154a3e8a8f2092469da29261479d115bc7db4a7794c8d59518f9a77186"),
    (2, 0, 896, "391a1e33d57bfe7283b4783df050ea51a751a0b61fb9d9050f5941fb40326c3f"),
    (289, 0, 896, "d87d01f6c48aebc7222f9bc18d1cee5981765f37363589140744b69ef6944653"),
)


def _fingerprint(rows) -> str:
    return canonical_json_hash(
        {
            "engine_version": ENGINE_VERSION,
            "chunk_elements": DEFAULT_CHUNK_ELEMENTS,
            "seed": SELFTEST_SEED,
            "schema_hash": SELFTEST_SCHEMA_HASH,
            "chunks": [list(row) for row in rows],
        }
    )


# What the noise of this recipe must look like. The recipe records it instead of a NumPy version number:
# two NumPy versions that give the same bytes have the same fingerprint, a version that changes the bytes does not.
EXPECTED_NOISE_FINGERPRINT = _fingerprint(GOLDEN_CHUNKS)


def compute_noise_fingerprint() -> str:
    """Generate the five chunks on THIS machine with THIS NumPy and fingerprint what came out (about 15 ms)."""
    rows = []
    for parameter_index, chunk_index, n, _ in GOLDEN_CHUNKS:
        address = ChunkNoiseAddress(
            SELFTEST_SEED, SELFTEST_SCHEMA_HASH, parameter_index, chunk_index, DEFAULT_CHUNK_ELEMENTS
        )
        noise = generate_chunk_noise(address, n)
        rows.append((parameter_index, chunk_index, n, hashlib.sha256(noise.tobytes()).hexdigest()))
    return _fingerprint(rows)


def noise_selftest() -> bool:
    """True if this machine generates the canonical noise bytes. A worker that fails must not receive candidates."""
    return compute_noise_fingerprint() == EXPECTED_NOISE_FINGERPRINT
