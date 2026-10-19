#!/usr/bin/env python3
"""Compare every active Python AST with a git revision; raw evidence and archives are excluded."""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import subprocess

EXCLUDED = ('docs/archive/', 'docs/evidence/', 'runtime/artifacts/', 'runtime/notebooks/')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[1]
    paths = subprocess.check_output(['git', 'ls-tree', '-r', '--name-only', args.base], cwd=repo, text=True).splitlines()
    results = []
    for name in paths:
        if not name.endswith(('.py', '.pyi')) or name.startswith(EXCLUDED):
            continue
        original = subprocess.check_output(['git', 'show', f'{args.base}:{name}'], cwd=repo)
        current = (repo / name).read_bytes()
        old = ast.dump(ast.parse(original), include_attributes=False)
        new = ast.dump(ast.parse(current), include_attributes=False)
        results.append({'path': name, 'equal': old == new,
                        'astSha256': hashlib.sha256(new.encode()).hexdigest()})
    changed = [item['path'] for item in results if not item['equal']]
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps({'base': args.base, 'files': results, 'changed': changed}, indent=2) + '\n')
    print(json.dumps({'files': len(results), 'changed': changed}))
    return bool(changed)


if __name__ == '__main__':
    raise SystemExit(main())
