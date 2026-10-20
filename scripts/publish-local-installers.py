#!/usr/bin/env python3
"""Prepare immutable installers; --prepare-only leaves the live download page untouched."""

import argparse
import gzip
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import tarfile
import time


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def cli_entries(packages, build, prepared=None):
    """Verify the complete CLI inventory before publishing any links (old app-only builds remain supported)."""
    path = packages / "cli/linux-worker.json"
    if prepared is None and not path.exists():
        return None
    names = {"installer": "install-worker.sh", "bundle": f"heteroes-worker-linux-{build}.tar.gz"}
    if prepared is None:
        receipt = json.loads(path.read_text())
        if receipt.get("build") != build or set(receipt.get("files", {})) != set(names.values()):
            raise RuntimeError("CLI build inventory differs")
        entries = {key: {"name": name, **receipt["files"][name]} for key, name in names.items()}
    else:
        entries = prepared
    if set(entries) != set(names):
        raise RuntimeError("CLI prepared inventory differs")
    result = {}
    for key, name in names.items():
        entry, file = entries[key], packages / "cli" / name
        if (
            entry.get("name") != name
            or not file.is_file()
            or file.stat().st_size != entry.get("sizeBytes")
            or sha(file) != entry.get("sha256")
        ):
            raise RuntimeError("CLI file differs from the reviewed receipt")
        result[key] = {
            "name": name,
            "url": "/downloads/" + name,
            "sha256": entry["sha256"],
            "sizeBytes": entry["sizeBytes"],
        }
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--packages", type=Path, required=True)
    parser.add_argument("--build", required=True)
    parser.add_argument("--receipt", type=Path)
    parser.add_argument("--volume-uuid", default="10443D1F443D094C")
    parser.add_argument(
        "--prepare-only", action="store_true", help="Build files and receipt without public links or manifest changes"
    )
    parser.add_argument(
        "--prepared-receipt", type=Path, help="Publish exactly these already prepared hashes; never rebuild them"
    )
    args = parser.parse_args(argv)
    if not re.fullmatch(r"[a-zA-Z0-9_-]+", args.build):
        parser.error("Build must contain only letters, numbers, underscores and hyphens")
    if args.prepared_receipt and (args.prepare_only or not args.receipt):
        parser.error("--prepared-receipt needs a distinct explicit --receipt and cannot be used with --prepare-only")
    if (
        subprocess.check_output(["findmnt", "-n", "-o", "UUID", "-T", str(args.packages)], text=True).strip()
        != args.volume_uuid
    ):
        raise RuntimeError("The selected installer disk is not mounted")
    repo = Path(__file__).resolve().parents[1]
    receipt = args.receipt or repo / "docs/evidence/2026-10-11-ui/installers.json"
    if receipt.exists() and args.receipt:
        raise RuntimeError("Existing receipt is never overwritten")
    links = repo / "frontend/public/downloads"
    if not args.prepare_only:
        links.mkdir(parents=True, exist_ok=True)
    manifest = {
        "version": "0.1.0",
        "build": args.build,
        "privateTrial": True,
        "nativeWindowsGpuVerified": False,
        "installers": [],
        "serverInstallers": [],
    }
    if args.prepare_only:
        manifest["publiclyPublished"] = False
    if args.prepared_receipt:
        prepared = json.loads(args.prepared_receipt.read_text())
        if prepared.get("build") != args.build or prepared.get("version") != "0.1.0":
            raise RuntimeError("Prepared receipt identity differs")
        # Verify every reviewed file before creating a link or replacing the live manifest.
        for key, kind, product in [
            ("installers", "worker", "HeteroES Worker"),
            ("serverInstallers", "server", "HeteroES Lab Server"),
        ]:
            entries = prepared.get(key, [])
            if len(entries) != 2 or {e.get("platform") for e in entries} != {"linux", "windows"}:
                raise RuntimeError("Prepared receipt inventory differs")
            for entry in entries:
                platform = entry["platform"]
                suffix = "Windows.exe" if platform == "windows" else "Linux.tar.gz"
                name = f"{product}-0.1.0-{args.build}-{suffix}"
                file = args.packages / kind / name
                if (
                    entry.get("name") != name
                    or not file.is_file()
                    or file.stat().st_size != entry.get("sizeBytes")
                    or sha(file) != entry.get("sha256")
                ):
                    raise RuntimeError("Prepared installer differs from the reviewed receipt")
                manifest[key].append(
                    {
                        "platform": platform,
                        "name": name,
                        "url": "/downloads/" + name,
                        "sha256": entry["sha256"],
                        "sizeBytes": entry["sizeBytes"],
                    }
                )
        manifest["publiclyPublished"] = True
        cli = cli_entries(args.packages, args.build, prepared.get("linuxWorker")) if "linuxWorker" in prepared else None
    else:
        cli = cli_entries(args.packages, args.build)
    if cli:
        manifest["linuxWorker"] = cli
    for kind, product, key in [
        ("worker", "HeteroES Worker", "installers"),
        ("server", "HeteroES Lab Server", "serverInstallers"),
    ]:
        if args.prepared_receipt:
            continue
        directory = args.packages / kind
        source = directory / f"{product} Setup 0.1.0.exe"
        windows = directory / f"{product}-0.1.0-{args.build}-Windows.exe"
        if windows.exists():
            if sha(windows) != sha(source):
                raise RuntimeError("Existing immutable Windows build differs; choose a new build name")
        else:
            shutil.copyfile(source, windows)
        linux = directory / f"{product}-0.1.0-{args.build}-Linux.tar.gz"
        if linux.exists():
            raise RuntimeError("Existing immutable Linux build; choose a new build name")
        with linux.open("xb") as raw, gzip.GzipFile(fileobj=raw, mode="wb", filename="", mtime=0) as compressed:
            with tarfile.open(fileobj=compressed, mode="w") as archive:

                def normalize(info):
                    info.uid = info.gid = info.mtime = 0
                    info.uname = info.gname = ""
                    executable = Path(info.name).name in {
                        "heteroes-" + kind,
                        "chrome-sandbox",
                        "chrome_crashpad_handler",
                    }
                    info.mode = 0o755 if info.isdir() or executable else 0o644
                    return info

                archive.add(directory / "linux-unpacked", arcname="heteroes-" + kind, filter=normalize)
        for platform, file in [("windows", windows), ("linux", linux)]:
            manifest[key].append(
                {
                    "platform": platform,
                    "name": file.name,
                    "url": "/downloads/" + file.name,
                    "sha256": sha(file),
                    "sizeBytes": file.stat().st_size,
                }
            )
    encoded = json.dumps(manifest, indent=2) + "\n"
    if not args.prepare_only:
        # Check every link first: a refused publication leaves the live page and its one-line installer unchanged.
        planned = [
            (args.packages / kind / entry["name"], links / entry["name"])
            for key, kind in [("installers", "worker"), ("serverInstallers", "server")]
            for entry in manifest[key]
        ]
        planned += [
            (args.packages / "cli" / entry["name"], links / entry["name"])
            for entry in manifest.get("linuxWorker", {}).values()
            if entry["name"] != "install-worker.sh"
        ]
        for file, link in planned:
            if (link.is_symlink() or link.exists()) and link.resolve() != file.resolve():
                raise RuntimeError("Existing download link points to another build")
        for file, link in planned:
            if not (link.is_symlink() or link.exists()):
                link.symlink_to(file.resolve())
        if "linuxWorker" in manifest:
            # This stable alias follows the reviewed build; versioned bundles stay for scripts already handed out.
            pending_link = links / "install-worker.sh.pending"
            pending_link.unlink(missing_ok=True)
            pending_link.symlink_to((args.packages / "cli/install-worker.sh").resolve())
            pending_link.replace(links / "install-worker.sh")
        else:
            # An app-only build (or a rollback to one) must not keep offering another build's command line installer.
            (links / "install-worker.sh").unlink(missing_ok=True)
        target = links / "manifest.json"
        if target.exists():
            shutil.copyfile(target, args.packages / f"previous-manifest-{time.time_ns()}.json")
        pending = links / "manifest.pending"
        pending.write_text(encoded)
        pending.replace(target)
    receipt.parent.mkdir(parents=True, exist_ok=True)
    receipt.write_text(encoded)
    print(
        json.dumps(
            {
                "build": args.build,
                "downloads": len(manifest["installers"]) + len(manifest["serverInstallers"]),
                "cloudPublish": False,
                "publiclyPublished": not args.prepare_only,
            }
        )
    )


if __name__ == "__main__":
    main()
