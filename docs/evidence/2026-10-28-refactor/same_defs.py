"""Every top-level definition of the old module (git HEAD) appears unchanged (AST) in exactly one of the new files."""
import ast, subprocess, sys
old_path, new_paths = sys.argv[1], sys.argv[2:]
def defs(text):
    out = {}
    for n in ast.parse(text).body:
        if isinstance(n, (ast.Import, ast.ImportFrom)) or (isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant)):
            continue
        key = getattr(n, "name", None) or ast.unparse(n.targets[0] if isinstance(n, ast.Assign) else n)[:60]
        out[key] = ast.dump(n)
    return out
old = defs(subprocess.run(["git", "show", __import__("os").environ.get("OLD_REV", "HEAD") + ":" + old_path], capture_output=True, text=True, check=True).stdout)
new = {}
for p in new_paths:
    for k, v in defs(open(p).read()).items():
        assert k not in new, ("twice", k); new[k] = v
bad = [k for k in old if new.get(k) != old[k]]
extra = [k for k in new if k not in old]
print(f"{len(old) - len(bad)}/{len(old)} definitions identical; changed/missing: {bad}; new: {extra}")
sys.exit(1 if bad or extra else 0)
