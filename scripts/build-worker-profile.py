#!/usr/bin/env python3
"""Generate reviewed, checksum-pinned first-install resources from pip reports.

Reports must be resolved for their target OS (pip --platform alone does not change
PEP 508 environment markers). No code from reports is executed by this generator.
"""

import argparse
import concurrent.futures
import gzip
import hashlib
import json
import pathlib
import tarfile
import urllib.request
import urllib.parse


def get_size(url):
    request = urllib.request.Request(url, headers={"User-Agent": "pip/25.0.1", "Range": "bytes=0-0"})
    with urllib.request.urlopen(request, timeout=60) as response:
        extent = response.headers.get("Content-Range")
        size = extent.rsplit("/", 1)[1] if extent else response.headers.get("Content-Length")
    if not size:
        raise ValueError("Missing object size: " + url)
    return int(size)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--track-a", type=pathlib.Path, required=True)
    parser.add_argument("--reports", type=pathlib.Path, required=True)
    args = parser.parse_args()
    root = pathlib.Path(__file__).resolve().parents[1]
    out = root / "desktop/worker/resources"
    out.mkdir(parents=True, exist_ok=True)
    with (
        (out / "runtime.tar.gz").open("wb") as raw,
        gzip.GzipFile(fileobj=raw, mode="wb", mtime=0, filename="") as compressed,
        tarfile.open(fileobj=compressed, mode="w") as archive,
    ):
        sources = list((args.track_a / "src/heteroes").rglob("*.py")) + [args.track_a / "scripts/run_worker.py"]
        for file in sorted(sources):
            info = archive.gettarinfo(str(file), str(file.relative_to(args.track_a)))
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            info.mtime = 0
            with file.open("rb") as stream:
                archive.addfile(info, stream)
    release = json.load(
        urllib.request.urlopen("https://api.github.com/repos/astral-sh/python-build-standalone/releases/tags/20261009")
    )
    platforms = {}
    for platform, target in [("windows", "x86_64-pc-windows-msvc"), ("linux", "x86_64-unknown-linux-gnu")]:
        name = f"cpython-3.12.15+20261009-{target}-install_only_stripped.tar.gz"
        asset = next(a for a in release["assets"] if a["name"] == name)
        report = json.loads((args.reports / f"{platform}.json").read_text())
        wheels = []
        lines = []
        for row in report["install"]:
            download = row["download_info"]
            url = download["url"]
            sha = download["archive_info"]["hashes"]["sha256"]
            filename = urllib.parse.unquote(urllib.parse.urlparse(url).path.rsplit("/", 1)[1])
            if not filename.endswith(".whl") or urllib.parse.urlparse(url).scheme != "https":
                raise ValueError("Only HTTPS wheels accepted")
            if platform == "windows" and ("manylinux" in filename or filename.startswith(("nvidia_", "triton-"))):
                raise ValueError("Linux-only wheel in Windows report")
            if "pypi.nvidia.com" in url:
                package = json.load(
                    urllib.request.urlopen(
                        f"https://pypi.org/pypi/{row['metadata']['name']}/{row['metadata']['version']}/json", timeout=30
                    )
                )
                public = next(
                    item
                    for item in package["urls"]
                    if item["filename"] == filename and item["digests"]["sha256"] == sha
                )
                url = public["url"]
                size = public["size"]
            else:
                size = None
                cached = args.reports / "cache-sizes.json"
                if cached.exists():
                    size = json.loads(cached.read_text()).get(sha)
            wheels.append({"name": filename, "url": url, "sha256": sha, **({"sizeBytes": size} if size else {})})
            lines.append(f"{row['metadata']['name']}=={row['metadata']['version']} --hash=sha256:{sha}")
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            sizes = list(pool.map(lambda wheel: wheel.get("sizeBytes") or get_size(wheel["url"]), wheels))
        for wheel, size in zip(wheels, sizes):
            wheel["sizeBytes"] = size
        lock = f"requirements-{platform}.txt"
        (out / lock).write_text("\n".join(sorted(lines)) + "\n")
        platforms[platform] = {
            "python": {
                "name": name,
                "url": asset["browser_download_url"],
                "sha256": asset["digest"].removeprefix("sha256:"),
                "sizeBytes": asset["size"],
            },
            "wheels": wheels,
            "lockFile": lock,
        }
    revision = "7ae557604adf67be50417f59c2c2f167def9a775"
    model = "Qwen/Qwen2.5-0.5B-Instruct"
    snapshot = pathlib.Path.home() / f".cache/huggingface/hub/models--Qwen--Qwen2.5-0.5B-Instruct/snapshots/{revision}"
    model_files = []
    for name in [
        "config.json",
        "generation_config.json",
        "model.safetensors",
        "tokenizer.json",
        "tokenizer_config.json",
        "vocab.json",
        "merges.txt",
    ]:
        file = snapshot / name
        sha = hashlib.sha256()
        with file.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                sha.update(chunk)
        model_files.append(
            {
                "name": name,
                "url": f"https://huggingface.co/{model}/resolve/{revision}/{name}",
                "sha256": sha.hexdigest(),
                "sizeBytes": file.stat().st_size,
            }
        )
    profile = {
        "version": 1,
        "profile": "desktop-v1",
        "pythonVersion": "3.12.15",
        "pythonRelease": "20261009",
        "modelId": model,
        "modelRevision": revision,
        "platforms": platforms,
        "modelFiles": model_files,
        "runtimeSha256": hashlib.sha256((out / "runtime.tar.gz").read_bytes()).hexdigest(),
    }
    (out / "profile.json").write_text(json.dumps(profile, indent=2) + "\n")
    reference = args.track_a / "artifacts/regression/2026-10-10-m3-native-profile/reference.json"
    (out / "reference.json").write_bytes(reference.read_bytes())
    print(
        "PASS pinned profile:",
        {
            p: {
                "wheels": len(v["wheels"]),
                "downloadBytes": sum(x["sizeBytes"] for x in v["wheels"])
                + v["python"]["sizeBytes"]
                + sum(x["sizeBytes"] for x in model_files),
            }
            for p, v in platforms.items()
        },
    )


if __name__ == "__main__":
    main()
