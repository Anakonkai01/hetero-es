"""Every file under <installed>/<sub> must be byte-identical to <source>/<sub-mapping>; prints counts and any difference.
    python3 -I installed_equals_source.py <installed dir> <source dir> [<installed dir> <source dir> ...]
A server runtime ships only the modules its backend imports, so the check goes installed -> source, not the reverse."""
import hashlib, sys
from pathlib import Path
bad = total = 0
for installed, source in zip(sys.argv[1::2], sys.argv[2::2]):
    for p in sorted(Path(installed).rglob("*.py")):
        if "__pycache__" in p.parts:
            continue
        q = Path(source) / p.relative_to(installed)
        total += 1
        if not q.is_file() or hashlib.sha256(p.read_bytes()).digest() != hashlib.sha256(q.read_bytes()).digest():
            bad += 1
            print("DIFFERS", p)
print(f"files={total} differing={bad}")
raise SystemExit(1 if bad else 0)
