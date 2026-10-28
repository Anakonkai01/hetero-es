"""SHA256 over every *.py below a directory (sorted relative paths, LC_ALL=C order): path NUL sha256 per file.
    python3 -I tree_hash.py <dir>      prints '<hash> <file count>'"""
import hashlib, sys
from pathlib import Path
root = Path(sys.argv[1])
files = sorted(p for p in root.rglob("*.py") if "__pycache__" not in p.parts)
digest = hashlib.sha256()
for p in files:
    digest.update(str(p.relative_to(root)).encode() + b"\0" + hashlib.sha256(p.read_bytes()).hexdigest().encode() + b"\n")
print(digest.hexdigest(), len(files))
