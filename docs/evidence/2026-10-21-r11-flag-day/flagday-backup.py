# Flag-day backup of the live r10 lab: writes ONLY into a new folder on the Archive disk; reads the live files.
import hashlib, json, os, sqlite3, subprocess, sys, tarfile, time
from pathlib import Path
H = Path.home()
out = Path("/mnt/Archive-2tb/heteroes-local/backups/r11-flag-day-20261021")
out.mkdir(mode=0o700)  # fails if it exists: never overwrite a backup
uuid = subprocess.run(["findmnt", "-no", "UUID", "/mnt/Archive-2tb"], capture_output=True, text=True).stdout.strip()
assert uuid == "10443D1F443D094C", uuid
live_db = H / ".config/heteroes-m2/state/product.sqlite"
# 1. consistent database snapshot through SQLite's backup API (the source opened read-only)
src = sqlite3.connect(f"file:{live_db}?mode=ro", uri=True); dst = sqlite3.connect(out / "product.sqlite")
src.backup(dst); dst.close(); src.close()
# 2. archives
def tar(name, root, exclude=()):
    with tarfile.open(out / name, "w:gz") as t:
        t.add(root, arcname=root.name, filter=lambda i: None if any(i.name.endswith(e) for e in exclude) else i)
tar("live-app.tar.gz", H / ".local/share/heteroes-lab/app")
tar("venv-backend.tar.gz", H / ".local/share/heteroes-lab/venv-backend")
tar("private-config.tar.gz", H / ".config/heteroes-m2", exclude=("state/product.sqlite", "state/product.sqlite-wal", "state/product.sqlite-shm"))
tar("systemd-unit.tar.gz", H / ".config/systemd/user/heteroes-lab.service")
app_head = subprocess.run(["git", "-C", str(H / ".local/share/heteroes-lab/app"), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
info = {"createdAt": time.time(), "liveAppCommit": app_head, "archiveUUID": uuid, "files": {}}
for f in sorted(out.iterdir()):
    os.chmod(f, 0o600)
    info["files"][f.name] = {"sha256": hashlib.sha256(f.read_bytes()).hexdigest(), "sizeBytes": f.stat().st_size}
(out / "backup.json").write_text(json.dumps(info, indent=1)); os.chmod(out / "backup.json", 0o600)
print(json.dumps(info, indent=1))
