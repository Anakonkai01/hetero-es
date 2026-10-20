#!/usr/bin/env python3
"""Build the headless Linux Worker: a pinned bundle and the one-line installer that fetches it.

    scripts/build-linux-worker.py --build lf1-20261020-cli1 --out <fresh directory> [--downloads https://lab/downloads]

The bundle holds exactly the desktop Worker's pinned resources (profile.json, lock file, reference, runtime.tar.gz),
so the CLI installs the same Python, wheels, model and runtime as the app. `install-worker.sh` carries the bundle's
SHA-256 and the pinned Python's URL and SHA-256; users run `curl -fsSL <downloads>/install-worker.sh | bash`.
"""

import argparse
import gzip
import hashlib
import io
import json
from pathlib import Path
import re
import tarfile

ROOT = Path(__file__).resolve().parents[1]
BUNDLE_FILES = (
    "profile.json",
    "requirements-linux.txt",
    "reference.json",
    "reference-v3-adapter.bin",
    "runtime.tar.gz",
)


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def build(resources, out, build_name, downloads):
    resources, out = Path(resources), Path(out)
    profile = json.loads((resources / "profile.json").read_text())
    if sha(resources / "runtime.tar.gz") != profile["runtimeSha256"]:
        raise RuntimeError("runtime.tar.gz does not match profile.json; refresh and commit the Worker resources")
    out.mkdir(parents=True, exist_ok=False)
    bundle = out / f"heteroes-worker-linux-{build_name}.tar.gz"
    # reproducible: fixed order, owner and times
    with bundle.open("wb") as raw, gzip.GzipFile(fileobj=raw, mode="wb", mtime=0, filename="") as compressed:
        with tarfile.open(fileobj=compressed, mode="w") as archive:
            for name in BUNDLE_FILES:
                data = (resources / name).read_bytes()
                info = tarfile.TarInfo("bundle/" + name)
                info.size, info.mode = len(data), 0o644
                archive.addfile(info, io.BytesIO(data))
    python = profile["platforms"]["linux"]["python"]
    values = {
        "BUILD": build_name,
        "BUNDLE_NAME": bundle.name,
        "BUNDLE_SHA256": sha(bundle),
        "PYTHON_URL": python["url"],
        "PYTHON_SHA256": python["sha256"],
        "DOWNLOADS": downloads.rstrip("/"),
    }
    script = (ROOT / "scripts/install-worker.sh.in").read_text()
    for key, value in values.items():
        if not re.fullmatch(r"[A-Za-z0-9_.:/%+-]+", value):
            raise ValueError("Unsafe value for " + key)
        script = script.replace("@" + key + "@", value)
    if re.search(r"@[A-Z0-9_]+@", script):
        raise RuntimeError("Unfilled placeholder in install-worker.sh")
    installer = out / "install-worker.sh"
    installer.write_text(script)
    installer.chmod(0o755)
    receipt = {"build": build_name, "downloads": values["DOWNLOADS"], "files": {}}
    for path in (bundle, installer):
        receipt["files"][path.name] = {"sha256": sha(path), "sizeBytes": path.stat().st_size}
    (out / "linux-worker.json").write_text(json.dumps(receipt, indent=2) + "\n")
    return receipt


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--build", required=True)
    parser.add_argument("--out", type=Path, required=True, help="a new directory")
    parser.add_argument("--downloads", default="https://lab.heteroes.site/downloads")
    parser.add_argument("--resources", type=Path, default=ROOT / "desktop/worker/resources")
    args = parser.parse_args(argv)
    if not re.fullmatch(r"[a-zA-Z0-9_-]+", args.build):
        parser.error("Build must contain only letters, numbers, underscores and hyphens")
    print(json.dumps(build(args.resources, args.out, args.build, args.downloads), indent=2))


if __name__ == "__main__":
    main()
