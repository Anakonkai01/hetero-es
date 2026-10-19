#!/usr/bin/env python3
"""Bundle CPU Server source/web and pin already downloaded Windows/Linux wheels."""

import argparse
from email.parser import BytesParser
import gzip
import hashlib
import json
from pathlib import Path
import shutil
import tarfile
import urllib.request
import zipfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheelhouse", type=Path, required=True)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[1]
    out = repo / "desktop/server/resources"
    out.mkdir(parents=True, exist_ok=True)
    worker = repo / "desktop/worker/resources"
    base = json.loads((worker / "profile.json").read_text())
    platforms = {}
    for platform in ("linux", "windows"):
        wheels = []
        lock = []
        for file in sorted((args.wheelhouse / platform).glob("*.whl")):
            with zipfile.ZipFile(file) as archive:
                metadata = next(name for name in archive.namelist() if name.endswith(".dist-info/METADATA"))
                data = BytesParser().parsebytes(archive.read(metadata))
            name, version = data["Name"], data["Version"]
            if name.lower().startswith(("torch", "nvidia", "triton", "transformers")):
                raise ValueError("Server dependency must be CPU-only")
            sha = hashlib.sha256(file.read_bytes()).hexdigest()
            with urllib.request.urlopen(f"https://pypi.org/pypi/{name}/{version}/json", timeout=30) as response:
                package = json.load(response)
            item = next(
                row for row in package["urls"] if row["filename"] == file.name and row["digests"]["sha256"] == sha
            )
            wheels.append({"name": file.name, "url": item["url"], "sha256": sha, "sizeBytes": file.stat().st_size})
            lock.append(f"{name}=={version} --hash=sha256:{sha}")
        if not wheels:
            raise ValueError("Empty wheelhouse")
        lock_file = f"requirements-{platform}.txt"
        (out / lock_file).write_text("\n".join(lock) + "\n")
        platforms[platform] = {"python": base["platforms"][platform]["python"], "wheels": wheels, "lockFile": lock_file}
    files = [(file, str(file.relative_to(repo))) for file in sorted((repo / "backend").glob("*.py"))]
    import sys

    sys.path.insert(0, str(repo))
    from backend.runtime_sources import shared_sources

    files += shared_sources(repo)
    files += [
        (file, "web/" + file.relative_to(repo / "frontend/dist").as_posix())
        for file in sorted((repo / "frontend/dist").rglob("*"))
        if file.is_file() and "downloads" not in file.relative_to(repo / "frontend/dist").parts
    ]
    if not (repo / "frontend/dist/index.html").is_file():
        raise ValueError("Build the web UI first")
    target = out / "runtime.tar.gz"
    with target.open("wb") as raw, gzip.GzipFile(fileobj=raw, mode="wb", mtime=0, filename="") as compressed:
        with tarfile.open(fileobj=compressed, mode="w") as archive:
            for file, name in files:
                info = archive.gettarinfo(str(file), name)
                info.uid = info.gid = info.mtime = 0
                info.uname = info.gname = ""
                with file.open("rb") as stream:
                    archive.addfile(info, stream)
    profile = {
        "version": 1,
        "profile": "server-cpu-v1",
        "pythonVersion": base["pythonVersion"],
        "pythonRelease": base["pythonRelease"],
        "platforms": platforms,
        "runtimeSha256": hashlib.sha256(target.read_bytes()).hexdigest(),
    }
    (out / "profile.json").write_text(json.dumps(profile, indent=2) + "\n")
    shutil.copyfile(worker / "tray.png", out / "tray.png")
    print(
        json.dumps(
            {
                "profile": profile["profile"],
                "runtimeSha256": profile["runtimeSha256"],
                "wheels": {p: len(row["wheels"]) for p, row in platforms.items()},
            }
        )
    )


if __name__ == "__main__":
    main()
