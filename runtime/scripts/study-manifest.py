#!/usr/bin/env python3
"""Generate a pinned safetensors file manifest from an existing local snapshot."""

import argparse
import json
from pathlib import Path
from heteroes.study.models import inspect, SUPPORTED_MODELS

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--model-path", type=Path, required=True)
parser.add_argument("--model-id", choices=SUPPORTED_MODELS, required=True)
parser.add_argument("--revision", required=True)
parser.add_argument("--output", type=Path, required=True)
args = parser.parse_args()
manifest = inspect(args.model_path, args.model_id, args.revision)
with args.output.open("x") as out:
    json.dump(manifest, out, indent=2)
print("Pinned", len(manifest["files"]), "model files; manifest contains checksums only.")
