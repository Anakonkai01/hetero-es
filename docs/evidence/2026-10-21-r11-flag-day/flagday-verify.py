# Verifies the flag-day backup: hashes, tar readability, database integrity and row counts, and a restore with the live
# lab's own restore-m2-metadata.py into a scratch folder (never into the live paths).
import hashlib, importlib.util, json, sqlite3, sys, tarfile, tempfile
from pathlib import Path
B = Path("/mnt/Archive-2tb/heteroes-local/backups/r11-flag-day-20261021"); H = Path.home()
info = json.loads((B / "backup.json").read_text())
for name, f in info["files"].items():
    ok = hashlib.sha256((B / name).read_bytes()).hexdigest() == f["sha256"]
    print("sha256", name, "OK" if ok else "DIFFERENT")
for name in ("live-app.tar.gz", "venv-backend.tar.gz", "private-config.tar.gz", "systemd-unit.tar.gz"):
    with tarfile.open(B / name) as t: print("tar", name, "members=", len(t.getmembers()))
db = sqlite3.connect(f"file:{B/'product.sqlite'}?mode=ro", uri=True)
print("integrity", db.execute("PRAGMA integrity_check").fetchone()[0])
live = sqlite3.connect(f"file:{H/'.config/heteroes-m2/state/product.sqlite'}?mode=ro", uri=True)
for t in ("users", "workspaces", "experiments", "devices", "assignments", "memberships"):
    a, b = db.execute(f"select count(*) from {t}").fetchone()[0], live.execute(f"select count(*) from {t}").fetchone()[0]
    print("rows", t, a, "live", b, "equal" if a == b else "DIFFERENT")
spec = importlib.util.spec_from_file_location("rm", H / ".local/share/heteroes-lab/app/scripts/restore-m2-metadata.py")
rm = importlib.util.module_from_spec(spec); spec.loader.exec_module(rm)
with tempfile.TemporaryDirectory(dir=sys.argv[1]) as tmp:
    data = (B / "product.sqlite").read_bytes()
    manifest = Path(tmp) / "manifest.json"
    manifest.write_text(json.dumps({"formatVersion": 1, "component": "heteroes-product-metadata", "sha256": hashlib.sha256(data).hexdigest(), "sizeBytes": len(data)}))
    result = rm.restore(B / "product.sqlite", manifest, Path(tmp) / "restored" / "product.sqlite")
    print("restore-m2-metadata into scratch:", "OK", type(result).__name__)
