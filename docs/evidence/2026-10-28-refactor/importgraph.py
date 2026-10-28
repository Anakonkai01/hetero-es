"""Reachability of HeteroES Python modules from the real entry points (AST imports + 'heteroes.x' strings).

usage: python3 importgraph.py <repo> [--why module]
Prints modules under runtime/src/heteroes and backend that no entry point reaches (tests excluded from roots).
"""

import ast
import re
import sys
from pathlib import Path

repo = Path(sys.argv[1]).resolve()
SRC = repo / "runtime/src"
STRING = re.compile(r"\b(heteroes(?:\.[a-z_0-9]+)+)")


def modname(path):
    if path.is_relative_to(SRC):
        parts = list(path.relative_to(SRC).with_suffix("").parts)
    elif path.is_relative_to(repo / "backend"):
        parts = ["backend", *path.relative_to(repo / "backend").with_suffix("").parts]
    else:
        return "file:" + str(path.relative_to(repo))
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


files = {}
for base in ["runtime/src/heteroes", "backend", "scripts", "acceptance", "runtime/scripts", "runtime/tests", "backend/tests",
             "runtime/notebooks", "runtime/docs"]:
    for p in (repo / base).rglob("*.py"):
        if "__pycache__" in p.parts:
            continue
        files[modname(p)] = p
modules = {m for m in files if not m.startswith("file:")}


def resolve(name):
    """Longest known module prefix of name, plus all parent packages."""
    out = set()
    parts = name.split(".")
    for i in range(len(parts), 0, -1):
        candidate = ".".join(parts[:i])
        if candidate in modules:
            out.add(candidate)
            for j in range(1, i):
                if ".".join(parts[:j]) in modules:
                    out.add(".".join(parts[:j]))
            break
    return out


def edges(mod, path):
    tree = ast.parse(path.read_text(encoding="utf-8"), str(path))
    pkg = mod.split(".") if path.name == "__init__.py" else mod.split(".")[:-1]
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                out |= resolve(a.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = pkg[: len(pkg) - node.level + 1] if node.level > 1 else pkg
                prefix = ".".join(base + ([node.module] if node.module else []))
            else:
                prefix = node.module or ""
            out |= resolve(prefix)
            for a in node.names:
                out |= resolve(prefix + "." + a.name)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            for m in STRING.findall(node.value):
                out |= resolve(m)
            # "backend.x" strings (uvicorn targets etc.)
            for m in re.findall(r"\b(backend(?:\.[a-z_0-9]+)+)", node.value):
                out |= resolve(m)
    return out


graph = {m: edges(m, p) for m, p in files.items()}

# strings in non-Python launchers (electron, shell, mjs) count as roots
extra = set()
for pattern in ["desktop/**/*.cjs", "desktop/**/*.ts", "desktop/**/*.js", "scripts/*.sh", "scripts/*.mjs", "scripts/*.cjs",
                "deploy/*", "packages/**/*.ts"]:
    for p in repo.glob(pattern):
        if "node_modules" in p.parts or not p.is_file():
            continue
        text = p.read_text(errors="ignore")
        for m in STRING.findall(text):
            extra |= resolve(m)

roots = set(extra)
roots |= {m for m in files if m.startswith("file:scripts/") or m.startswith("file:acceptance/")}
roots |= {"heteroes.v3.__main__", "heteroes.__main__", "backend.app", "backend.server" if "backend.server" in files else "backend",
          "heteroes.sdk", "heteroes.sdk_lab", "file:runtime/scripts/run_worker.py"}
roots |= {m for m in modules if m.endswith("__main__")}
roots &= set(files)

seen, stack, parent = set(), list(roots), {r: None for r in roots}
while stack:
    m = stack.pop()
    if m in seen:
        continue
    seen.add(m)
    for n in graph.get(m, ()):
        if n not in seen:
            parent.setdefault(n, m)
            stack.append(n)

if "--why" in sys.argv:
    m = sys.argv[sys.argv.index("--why") + 1]
    chain = []
    while m:
        chain.append(m)
        m = parent.get(m)
    print(" <- ".join(chain))
    sys.exit()

unreached = sorted(m for m in modules if m not in seen)
for m in unreached:
    importers = sorted(k for k, v in graph.items() if m in v)
    lines = len(files[m].read_text().splitlines())
    print(f"{m:55s} {lines:5d}  imported by: {', '.join(importers)[:160]}")
print(len(unreached), "unreached of", len(modules))
