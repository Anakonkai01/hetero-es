"""Move the strict engine modules from heteroes/eval to heteroes/strict and rewrite every reference.

usage: python3 move_strict.py <repo> snapshot <out.json>   # AST-without-imports digest per strict module
       python3 move_strict.py <repo> move
       python3 move_strict.py <repo> compare <before.json> <after.json>
"""

import ast
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

repo = Path(sys.argv[1]).resolve()
STRICT = [
    "attention_stages", "frozen_int8", "frozen_int8_cuda", "frozen_int8_decoder", "integer_cuda", "integer_decoder",
    "integer_lm_head", "integer_plan", "integer_reference", "integer_tma", "qwen2_reference", "qwen2_strict_cuda",
    "reference_ops", "strict_backend", "strict_cuda", "strict_decode_cuda", "strict_decoder", "strict_decoder_graph",
    "strict_decoder_packed", "strict_prefill_cuda",
]
NAMES = "|".join(STRICT)


def digest(path):
    """sha256 of the module AST with every import statement removed, plus a separate hash of its long strings."""
    tree = ast.parse(path.read_text(encoding="utf-8"))

    class Drop(ast.NodeTransformer):
        def visit_Import(self, node):
            return ast.Pass()

        def visit_ImportFrom(self, node):
            return ast.Pass()

    strings = [n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str) and len(n.value) > 200]
    body = ast.dump(Drop().visit(tree))
    return {
        "astWithoutImports": hashlib.sha256(body.encode()).hexdigest(),
        "longStrings": hashlib.sha256("\0".join(strings).encode()).hexdigest(),
        "longStringCount": len(strings),
    }


def files():
    out = subprocess.run(["git", "-C", str(repo), "ls-files"], capture_output=True, text=True, check=True).stdout.split()
    return [repo / f for f in out if f.endswith((".py", ".json", ".md", ".toml", ".sh")) and (repo / f).is_file()]


def rewrite(text):
    text = re.sub(rf"\bheteroes\.eval\.({NAMES})\b", r"heteroes.strict.\1", text)
    text = re.sub(rf"\bheteroes/eval/({NAMES})\.py\b", r"heteroes/strict/\1.py", text)

    def from_list(m):
        names = [n.strip() for n in m.group(2).split(",")]
        mods = [n.split()[0] for n in names]
        strict = [n in STRICT for n in mods]
        if all(strict):
            return f"{m.group(1)}from heteroes.strict import {m.group(2)}"
        if any(strict):
            raise SystemExit(f"mixed import: {m.group(0)}")
        return m.group(0)

    return re.sub(r"^(\s*)from heteroes\.eval import ([a-z_0-9 ,]+?)\s*$", from_list, text, flags=re.M)


mode = sys.argv[2]
if mode == "snapshot":
    base = repo / "runtime/src/heteroes"
    where = {m: (base / "strict" / f"{m}.py") if (base / "strict" / f"{m}.py").exists() else base / "eval" / f"{m}.py" for m in STRICT}
    Path(sys.argv[3]).write_text(json.dumps({m: digest(p) for m, p in where.items()}, indent=1, sort_keys=True))
elif mode == "move":
    src = repo / "runtime/src/heteroes"
    (src / "strict").mkdir(exist_ok=True)
    for m in STRICT:
        subprocess.run(["git", "-C", str(repo), "mv", f"runtime/src/heteroes/eval/{m}.py", f"runtime/src/heteroes/strict/{m}.py"], check=True)
    changed = 0
    for f in files():
        if "fixtures" in f.parts or "receipts" in f.parts:
            continue
        old = f.read_text(encoding="utf-8")
        new = rewrite(old)
        if new != old:
            f.write_text(new, encoding="utf-8")
            changed += 1
    print("rewrote", changed, "files")
elif mode == "compare":
    a, b = json.loads(Path(sys.argv[3]).read_text()), json.loads(Path(sys.argv[4]).read_text())
    bad = [m for m in STRICT if a[m] != b[m]]
    for m in STRICT:
        print(("SAME " if a[m] == b[m] else "DIFF ") + m, a[m]["longStringCount"])
    sys.exit(1 if bad else 0)
