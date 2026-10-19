#!/usr/bin/env python3
"""Compare the hash fields of cuda_engine_crossgpu.py files: python compare_cudaengine.py REFERENCE.json OTHER.json [...]. Exit 1 if any differs."""
import json
import sys


def hashes(node, prefix=""):
    found = {}
    for key, value in node.items():
        if isinstance(value, dict):
            found.update(hashes(value, prefix + key + "."))
        elif isinstance(value, str) and len(value) >= 40:
            found[prefix + key] = value
    return found


reference = hashes(json.load(open(sys.argv[1])))
print(f"{len(reference)} hash fields in {sys.argv[1]}")
status = 0
for path in sys.argv[2:]:
    other = hashes(json.load(open(path)))
    equal = other == reference
    print(f"{path}: {'equal' if equal else 'DIFFERENT'} ({len(other)} fields)")
    status |= 0 if equal else 1
sys.exit(status)
