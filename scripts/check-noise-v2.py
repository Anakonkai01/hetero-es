#!/usr/bin/env python3
"""CPU-only cross-platform source/installed-runtime probe; never starts CUDA.

Run with PYTHONPATH set to the runtime being checked, CUDA_VISIBLE_DEVICES='',
and --out pointing to a fresh receipt. Native Windows must use Windows Python.
"""

import argparse
import hashlib
import json
from pathlib import Path
import platform
import sys

import numpy as np

from heteroes.noise.contracts import ENGINE_V2, EXPECTED_V2_NOISE_FINGERPRINT
from heteroes.noise.engine_v2 import TABLE_SHA256, THRESHOLDS, transform_words
from heteroes.noise.selftest import compute_noise_fingerprint as legacy_fingerprint
from heteroes.noise.selftest_v2 import compute_noise_fingerprint
from heteroes.product.cpu_coordinator import check_update
from heteroes.product.recovery import source_identity


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        raise FileExistsError("Receipt already exists")
    values = {0, 2**31 - 1}
    values.update(int(t) + offset for t in THRESHOLDS for offset in (-1, 0, 1) if 0 <= int(t) + offset < 2**31)
    values.update(
        i * 32768 + offset for i in range(65536) for offset in (-1, 0, 32767) if 0 <= i * 32768 + offset < 2**31
    )
    words = np.array(sorted(values) + [v | 2**31 for v in sorted(values)], dtype="<u4")
    magnitude = np.searchsorted(np.array(THRESHOLDS, dtype="<u4"), words & np.uint32(0x7FFFFFFF), side="right")
    reference = magnitude.astype("<u2") | ((words >> np.uint32(31)).astype("<u2") << np.uint16(15))
    output = transform_words(words)
    if output.tobytes() != reference.tobytes():
        raise ValueError("Boundary lookup differs from independent searchsorted reference")
    fingerprint = compute_noise_fingerprint()
    if fingerprint != EXPECTED_V2_NOISE_FINGERPRINT:
        raise ValueError("V2 golden fingerprint differs")
    known_answer = check_update(ENGINE_V2)
    import heteroes
    import torch

    result = {
        "formatVersion": 1,
        "scope": "CPU-only noise boundaries, golden vectors and non-power-of-two update; no GPU acceptance",
        "platform": sys.platform,
        "python": platform.python_version(),
        "executable": sys.executable,
        "libc": list(platform.libc_ver()),
        "numpy": np.__version__,
        "torch": torch.__version__,
        "sourceTreeSha256": source_identity(Path(heteroes.__file__).parent)["sourceTreeSha256"],
        "portableSourceTreeSha256": hashlib.sha256(
            json.dumps(
                {
                    k.replace(chr(92), "/"): v
                    for k, v in source_identity(Path(heteroes.__file__).parent)["sourceFiles"].items()
                },
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest(),
        "engine": ENGINE_V2,
        "tableSha256": TABLE_SHA256,
        "fingerprint": fingerprint,
        "legacyFingerprint": legacy_fingerprint(),
        "boundaryWords": int(words.size),
        "boundarySha256": hashlib.sha256(output.tobytes()).hexdigest(),
        "updateKnownAnswer": known_answer,
        "passed": True,
    }
    args.out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
