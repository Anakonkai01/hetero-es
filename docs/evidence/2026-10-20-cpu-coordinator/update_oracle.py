"""Independent NumPy update oracle; no production update, no model downloads, no GPU."""

import hashlib
import json

import numpy as np
import torch

from heteroes.model.schema import build_parameter_schema
from heteroes.noise.contracts import ParameterNoiseAddress
from heteroes.noise.engine import generate_chunk_noise, ChunkNoiseAddress


def main():
    baseline = ((np.arange(200_003, dtype=np.int32) % 251 - 125) / 4096).astype(np.float16)
    model = torch.nn.Module()
    model.register_parameter("w", torch.nn.Parameter(torch.from_numpy(baseline.copy())))
    schema = build_parameter_schema(model)
    acc = np.zeros(len(baseline), dtype=np.float32)
    for seed, coefficient in zip((5, 6, 7), (1.0, -0.5, 0.25)):
        chunks = [generate_chunk_noise(ChunkNoiseAddress(seed, schema.hash, 0, index, 65536),
                                       min(65536, len(baseline) - index * 65536))
                  for index in range((len(baseline) + 65535) // 65536)]
        acc = acc + np.concatenate(chunks).astype(np.float32) * np.float32(coefficient)
    expected = (baseline.astype(np.float32) + (acc * (np.float32(1) / np.float32(3))) * np.float32(0.05)).astype(np.float16)
    old_division = (baseline.astype(np.float32) + (acc / np.float32(3)) * np.float32(0.05)).astype(np.float16)
    print(json.dumps({"schemaHash": schema.hash,
                      "parentSha256": hashlib.sha256(baseline.tobytes()).hexdigest(),
                      "updatedSha256": hashlib.sha256(expected.tobytes()).hexdigest(),
                      "trueDivisionDifferentElements": int(np.count_nonzero(expected.view(np.uint16) != old_division.view(np.uint16)))}, indent=2))


if __name__ == "__main__":
    main()
