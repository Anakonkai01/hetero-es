#!/usr/bin/env python3
"""Generate reviewed, checksum-pinned first-install resources from pip reports.

    build-worker-profile.py --track-a runtime --reports <dir with linux.json, windows.json> \\
        --profile desktop-v3 --reference-dir <dir with reference-v3.json and its adapter> --out <new directory>

Reports must be resolved for their target OS (pip --platform alone does not change
PEP 508 environment markers). No code from reports is executed by this generator.
The output directory must not exist: resources are reviewed there and copied into
desktop/worker/resources separately. desktop-v1 keeps the legacy reference; desktop-v3
ships the selected v3 reference as reference.json beside its pinned adapter file.
"""

import argparse
import concurrent.futures
import gzip
import hashlib
import json
import pathlib
import shutil
import tarfile
import urllib.request
import urllib.parse

REVISION = "7ae557604adf67be50417f59c2c2f167def9a775"
MODEL = "Qwen/Qwen2.5-0.5B-Instruct"
MODEL_FILES = [
    "config.json",
    "generation_config.json",
    "model.safetensors",
    "tokenizer.json",
    "tokenizer_config.json",
    "vocab.json",
    "merges.txt",
]
LEGACY_REFERENCE = "artifacts/regression/2026-10-10-m3-native-profile/reference.json"


def get_size(url):
    request = urllib.request.Request(url, headers={"User-Agent": "pip/25.0.1", "Range": "bytes=0-0"})
    with urllib.request.urlopen(request, timeout=60) as response:
        extent = response.headers.get("Content-Range")
        size = extent.rsplit("/", 1)[1] if extent else response.headers.get("Content-Length")
    if not size:
        raise ValueError("Missing object size: " + url)
    return int(size)


def fetch_release():
    return json.load(
        urllib.request.urlopen("https://api.github.com/repos/astral-sh/python-build-standalone/releases/tags/20261009")
    )


def public_wheel(name, version, filename, sha):
    package = json.load(urllib.request.urlopen(f"https://pypi.org/pypi/{name}/{version}/json", timeout=30))
    return next(item for item in package["urls"] if item["filename"] == filename and item["digests"]["sha256"] == sha)


def file_sha256(path):
    sha = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            sha.update(chunk)
    return sha.hexdigest()


def write_runtime(track_a, out):
    with (
        (out / "runtime.tar.gz").open("wb") as raw,
        gzip.GzipFile(fileobj=raw, mode="wb", mtime=0, filename="") as compressed,
        tarfile.open(fileobj=compressed, mode="w") as archive,
    ):
        sources = list((track_a / "src/heteroes").rglob("*.py")) + [track_a / "scripts/run_worker.py"]
        for file in sorted(sources):
            info = archive.gettarinfo(str(file), str(file.relative_to(track_a)))
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            info.mtime = 0
            with file.open("rb") as stream:
                archive.addfile(info, stream)


def platform_entry(platform, target, release, report, reports, out, pinned):
    """`pinned` maps exact wheel URLs of a reviewed profile to their SHA-256, for report rows without a hash."""
    name = f"cpython-3.12.15+20261009-{target}-install_only_stripped.tar.gz"
    asset = next(a for a in release["assets"] if a["name"] == name)
    wheels = []
    lines = []
    for row in report["install"]:
        download = row["download_info"]
        url = download["url"]
        sha = download.get("archive_info", {}).get("hashes", {}).get("sha256") or pinned.get(url)
        if not sha:
            raise ValueError("The report has no hash for " + url + " and no reviewed profile pins that URL")
        filename = urllib.parse.unquote(urllib.parse.urlparse(url).path.rsplit("/", 1)[1])
        if not filename.endswith(".whl") or urllib.parse.urlparse(url).scheme != "https":
            raise ValueError("Only HTTPS wheels accepted")
        if platform == "windows" and ("manylinux" in filename or filename.startswith(("nvidia_", "triton-"))):
            raise ValueError("Linux-only wheel in Windows report")
        if "pypi.nvidia.com" in url:
            public = public_wheel(row["metadata"]["name"], row["metadata"]["version"], filename, sha)
            url = public["url"]
            size = public["size"]
        else:
            size = None
            cached = reports / "cache-sizes.json"
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
    return {
        "python": {
            "name": name,
            "url": asset["browser_download_url"],
            "sha256": asset["digest"].removeprefix("sha256:"),
            "sizeBytes": asset["size"],
        },
        "wheels": wheels,
        "lockFile": lock,
    }


def write_reference(profile, track_a, reference_dir, out):
    if profile == "desktop-v1":
        (out / "reference.json").write_bytes((track_a / LEGACY_REFERENCE).read_bytes())
        return
    reference = json.loads((reference_dir / "reference-v3.json").read_text())
    if reference.get("formatVersion") != 3 or reference.get("profile") != profile:
        raise ValueError("The selected reference is not a desktop-v3 reference")
    adapter = pathlib.Path(reference["adapter"]["file"]).name
    if file_sha256(reference_dir / adapter) != reference["adapter"]["sha256"]:
        raise ValueError("The reference adapter file differs from its pinned hash")
    shutil.copyfile(reference_dir / "reference-v3.json", out / "reference.json")
    shutil.copyfile(reference_dir / adapter, out / adapter)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--track-a", type=pathlib.Path, required=True)
    parser.add_argument("--reports", type=pathlib.Path, required=True)
    parser.add_argument("--profile", choices=["desktop-v1", "desktop-v3"], required=True)
    parser.add_argument("--reference-dir", type=pathlib.Path, help="desktop-v3 only")
    parser.add_argument("--out", type=pathlib.Path, required=True, help="a new directory")
    parser.add_argument(
        "--pinned-profile",
        type=pathlib.Path,
        help="a reviewed profile.json whose hash is used for a report row without one, only for the identical URL",
    )
    parser.add_argument(
        "--model-snapshot",
        type=pathlib.Path,
        default=pathlib.Path.home()
        / f".cache/huggingface/hub/models--Qwen--Qwen2.5-0.5B-Instruct/snapshots/{REVISION}",
    )
    args = parser.parse_args(argv)
    if (args.profile == "desktop-v3") != (args.reference_dir is not None):
        raise ValueError("--reference-dir is required for desktop-v3 and refused for desktop-v1")
    if args.out.exists():
        raise FileExistsError(args.out)
    partial = args.out.with_name(args.out.name + ".partial")
    partial.mkdir(parents=True)  # a leftover partial directory from a crash is refused too
    try:
        write_reference(args.profile, args.track_a, args.reference_dir, partial)
        write_runtime(args.track_a, partial)
        release = fetch_release()
        reviewed = json.loads(args.pinned_profile.read_text())["platforms"] if args.pinned_profile else {}
        platforms = {}
        for platform, target in [("windows", "x86_64-pc-windows-msvc"), ("linux", "x86_64-unknown-linux-gnu")]:
            report = json.loads((args.reports / f"{platform}.json").read_text())
            pinned = {wheel["url"]: wheel["sha256"] for wheel in reviewed.get(platform, {}).get("wheels", [])}
            platforms[platform] = platform_entry(platform, target, release, report, args.reports, partial, pinned)
        model_files = [
            {
                "name": name,
                "url": f"https://huggingface.co/{MODEL}/resolve/{REVISION}/{name}",
                "sha256": file_sha256(args.model_snapshot / name),
                "sizeBytes": (args.model_snapshot / name).stat().st_size,
            }
            for name in MODEL_FILES
        ]
        profile = {
            "version": 1,
            "profile": args.profile,
            "pythonVersion": "3.12.15",
            "pythonRelease": "20261009",
            "modelId": MODEL,
            "modelRevision": REVISION,
            "platforms": platforms,
            "modelFiles": model_files,
            "runtimeSha256": file_sha256(partial / "runtime.tar.gz"),
        }
        (partial / "profile.json").write_text(json.dumps(profile, indent=2) + "\n")
    except BaseException:
        shutil.rmtree(partial)
        raise
    partial.rename(args.out)
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
