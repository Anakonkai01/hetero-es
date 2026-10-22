"""Finding 13: replay a run's ledger updates and, for one generation, record per-tensor weight hashes and per-(seed, tensor) noise hashes.

    python diag_update.py <run dir> <model dir> <experiment> <generation> <out.json> [--dump-tensor I]

Run on two machines and diff the outputs to find the first tensor (and seed) whose bits differ. Read-only on the run dir.
"""

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import torch

from heteroes.es.update import apply_coefficients_
from heteroes.eval.candidate import model_weights_sha256
from heteroes.ledger import Ledger
from heteroes.model.schema import resolve_tensors
from heteroes.noise.contracts import ParameterNoiseAddress
from heteroes.noise.engine import chunk_length, generate_chunk_noise, num_chunks
from heteroes.v3.model import load, trainable_schema


def tensor_sha(tensor):
    return hashlib.sha256(tensor.detach().contiguous().view(torch.int16).cpu().numpy().tobytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    for name in ("run", "model", "experiment", "generation", "out"):
        parser.add_argument(name)
    parser.add_argument("--dump-tensor", type=int, action="append", default=[])
    args = parser.parse_args()
    root, target = Path(args.run), int(args.generation)
    recipe = json.loads((root / "recipe.json").read_text())
    chunk_elements = recipe["noise"]["chunkElements"]
    model, _tokenizer = load(args.model, recipe["model"]["files"], "cuda")
    schema = trainable_schema(model, recipe["weightSpace"])
    out = {"base": model_weights_sha256(model, schema), "children": []}
    with Ledger(root / "ledger.sqlite") as ledger:
        for generation in range(target + 1):
            update = ledger.get_update(args.experiment, generation)
            seeds, coefficients = update.record.update_inputs()
            if generation == target:
                tensors = resolve_tensors(model, schema)
                out["seeds"] = [int(s) for s in seeds]
                out["coefficients"] = [float(c) for c in coefficients]
                out["alpha"] = update.record.alpha
                out["parentTensors"] = [tensor_sha(t) for t in tensors]
                noise = {}
                for entry, tensor in zip(schema.entries, tensors):
                    numel = tensor.numel()
                    row = []
                    for seed in seeds:
                        digest = hashlib.sha256()
                        for chunk in range(num_chunks(numel, chunk_elements)):
                            address = ParameterNoiseAddress(
                                candidate_seed=seed,
                                schema_hash=schema.hash,
                                parameter_index=entry.index,
                                chunk_elements=chunk_elements,
                            ).chunk(chunk)
                            digest.update(generate_chunk_noise(address, chunk_length(numel, chunk, chunk_elements)).tobytes())
                        row.append(digest.hexdigest()[:16])
                    noise[entry.index] = row
                out["noise"] = noise
            apply_coefficients_(model, schema, seeds, coefficients, update.record.alpha, chunk_elements)
            child = model_weights_sha256(model, schema)
            out["children"].append({"generation": generation, "child": child, "ledger": update.child_weights_sha256})
            print(generation, child == update.child_weights_sha256, child[:12], flush=True)
            if generation == target:
                tensors = resolve_tensors(model, schema)
                out["childTensors"] = [tensor_sha(t) for t in tensors]
                out["names"] = [entry.canonical_name for entry in schema.entries]
                for index in args.dump_tensor:
                    np.save(root / f"tensor-{index}-{out['base'][:4]}.npy", tensors[index].detach().cpu().numpy())
    Path(args.out).write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
