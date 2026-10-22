"""Finding 13: the noise chunks of one (tensor, seed), as float32 and as float16, hashed per chunk; differing elements dumped.

    python diag_noise.py <run dir> <model dir> <tensor index> <seed> <out.json> [--repeat N] [--chunks a,b]

Without --chunks every chunk is hashed; with it those chunks are also saved (f32 and f16) next to the output.
"""

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

from heteroes.noise.contracts import ParameterNoiseAddress
from heteroes.noise.engine import chunk_length, derive_chunk_seed, num_chunks
from heteroes.v3.model import load, trainable_schema


def main():
    parser = argparse.ArgumentParser()
    for name in ("run", "model", "tensor", "seed", "out"):
        parser.add_argument(name)
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--chunks", default="")
    args = parser.parse_args()
    root = Path(args.run)
    recipe = json.loads((root / "recipe.json").read_text())
    chunk_elements = recipe["noise"]["chunkElements"]
    model, _ = load(args.model, recipe["model"]["files"], "cpu")
    schema = trainable_schema(model, recipe["weightSpace"])
    entry = schema.entries[int(args.tensor)]
    chosen = {int(c) for c in args.chunks.split(",") if c}
    rows = []
    for chunk in range(num_chunks(entry.numel, chunk_elements)):
        if chosen and chunk not in chosen:
            continue
        address = ParameterNoiseAddress(
            candidate_seed=int(args.seed), schema_hash=schema.hash, parameter_index=entry.index, chunk_elements=chunk_elements
        ).chunk(chunk)
        n = chunk_length(entry.numel, chunk, chunk_elements)
        seen = set()
        for _ in range(args.repeat):
            f32 = np.random.Generator(np.random.PCG64(seed=derive_chunk_seed(address))).standard_normal(n, dtype=np.float32)
            f16 = f32.astype(np.float16, copy=False)
            seen.add((hashlib.sha256(f32.tobytes()).hexdigest()[:16], hashlib.sha256(f16.tobytes()).hexdigest()[:16]))
        rows.append({"chunk": chunk, "hashes": sorted(seen)})
        if chunk in chosen:
            np.save(root / f"noise-{args.tensor}-{args.seed}-{chunk}-f32.npy", f32)
            np.save(root / f"noise-{args.tensor}-{args.seed}-{chunk}-f16.npy", f16)
    Path(args.out).write_text(json.dumps({"name": entry.canonical_name, "numel": entry.numel, "rows": rows}, indent=1))


if __name__ == "__main__":
    main()
