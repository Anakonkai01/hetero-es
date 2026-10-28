"""Move top-level definitions (with their leading comments) from one module into a new one, text unchanged.

usage: python3 split_module.py <source.py> <target.py> <docstring> <name> [<name> ...]
The target gets: docstring, then the moved blocks in their original order. Imports are fixed afterwards by hand
(ruff F401/F821 list what is missing or unused). Prints the AST dump hash of every moved node before the move so a
later check can prove the bodies are unchanged.
"""

import ast
import hashlib
import sys
from pathlib import Path

source, target, doc, names = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3], set(sys.argv[4:])
text = source.read_text()
lines = text.splitlines(keepends=True)
tree = ast.parse(text)


def node_names(node):
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return {node.name}
    if isinstance(node, ast.Assign):
        return {t.id for t in node.targets if isinstance(t, ast.Name)}
    return set()


spans, found = [], set()
body = tree.body
for i, node in enumerate(body):
    if node_names(node) & names:
        start = (node.decorator_list[0].lineno if getattr(node, "decorator_list", None) else node.lineno) - 1
        # include comment lines directly above (section markers)
        while start > 0 and lines[start - 1].lstrip().startswith("#"):
            start -= 1
        end = node.end_lineno
        spans.append((start, end))
        found |= node_names(node)
        print(node_names(node), hashlib.sha256(ast.dump(node).encode()).hexdigest()[:16])
missing = names - found
if missing:
    raise SystemExit(f"not found: {missing}")
moved = "".join("".join(lines[s:e]) + "\n\n" for s, e in spans)
keep = list(lines)
for s, e in reversed(spans):
    del keep[s:e]
    # drop the blank lines left behind (keep at most two)
    while s < len(keep) and keep[s].strip() == "" and s > 1 and keep[s - 1].strip() == "" and keep[s - 2].strip() == "":
        del keep[s]
source.write_text("".join(keep))
target.write_text(f'"""{doc}"""\n\n' + moved.rstrip() + "\n")
