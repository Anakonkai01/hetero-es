#!/usr/bin/env python3
"""Independent encrypted session copy with a full restore/hash verification.

Secrets and the randomly generated recovery key stay outside source control.
The destination must be on the owner-selected Archive-2tb filesystem.
"""

import argparse
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import secrets
import shutil
import subprocess
import tarfile
import tempfile

ARCHIVE_UUID = "10443D1F443D094C"


def sha256(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def check_destination(path):
    path = path.resolve(strict=True)
    result = subprocess.run(
        ["findmnt", "-rn", "-T", str(path), "-o", "SOURCE"],
        check=True,
        capture_output=True,
        text=True,
    )
    expected = Path("/dev/disk/by-uuid") / ARCHIVE_UUID
    if not expected.exists() or Path(result.stdout.strip()).resolve() != expected.resolve():
        raise ValueError("Destination is not on the selected Archive-2tb UUID")
    return path


def private_key(path):
    if path.is_symlink():
        raise ValueError("Recovery key must not be a symlink")
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.parent.chmod(0o700)
    if not path.exists():
        with path.open("x") as stream:
            os.chmod(path, 0o600)
            stream.write(secrets.token_urlsafe(48) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
    if path.stat().st_mode & 0o077:
        raise ValueError("Recovery key must have mode 0600")
    # It must survive independently of the removable archive filesystem.
    result = subprocess.run(
        ["findmnt", "-rn", "-T", str(path), "-o", "SOURCE"], check=True, capture_output=True, text=True
    )
    if Path(result.stdout.strip()).resolve() == Path("/dev/disk/by-uuid", ARCHIVE_UUID).resolve():
        raise ValueError("Store the recovery key separately from Archive-2tb")


def gpg_args(key):
    return ["gpg", "--batch", "--no-symkey-cache", "--pinentry-mode", "loopback", "--passphrase-file", str(key)]


def create(source, destination, key, extra_files):
    source = source.resolve(strict=True)
    files = {}
    for path in sorted(source.rglob("*")):
        if path.is_symlink() or (not path.is_dir() and not path.is_file()):
            raise ValueError("Source contains a symlink or special file")
        if path.is_file():
            files[path.relative_to(source).as_posix()] = path
    for path in extra_files:
        if path.is_symlink() or not path.is_file():
            raise ValueError("Extra private file must be regular")
        name = "session-private/" + path.name
        if name in files:
            raise ValueError("Duplicate extra file name")
        files[name] = path
    if not files or "archive-manifest.json" in files:
        raise ValueError("Empty source or reserved manifest name")
    manifest = {
        "formatVersion": 1,
        "component": "heteroes-encrypted-session",
        "files": {name: {"sha256": sha256(path), "sizeBytes": path.stat().st_size} for name, path in files.items()},
    }
    required = sum(item["sizeBytes"] for item in manifest["files"].values())
    if shutil.disk_usage(destination.parent).free < required * 2 + 128 * 1024**2:
        raise ValueError("Insufficient archive and restore-test space")
    if destination.exists():
        raise FileExistsError("Refusing to replace an existing archive")
    fd, temporary = tempfile.mkstemp(prefix=".archive-", dir=destination.parent)
    os.close(fd)
    temporary = Path(temporary)
    process = subprocess.Popen(
        gpg_args(key) + ["--symmetric", "--cipher-algo", "AES256"],
        stdin=subprocess.PIPE,
        stdout=temporary.open("wb"),
        stderr=subprocess.PIPE,
    )
    try:
        with tarfile.open(fileobj=process.stdin, mode="w|gz", dereference=True) as archive:
            data = json.dumps(manifest, sort_keys=True).encode()
            entry = tarfile.TarInfo("archive-manifest.json")
            entry.size, entry.mode = len(data), 0o600
            archive.addfile(entry, io.BytesIO(data))
            for name, path in files.items():
                # Every entry is regular even when the source uses hardlinks.
                entry = tarfile.TarInfo(name)
                entry.size, entry.mode = path.stat().st_size, 0o600
                with path.open("rb") as stream:
                    archive.addfile(entry, stream)
        process.stdin.close()
        error = process.stderr.read()
        if process.wait():
            raise RuntimeError("Encryption failed: " + error.decode(errors="replace"))
        restored = verify(temporary, destination.parent, key)
        # Atomic no-replace publication, including on NTFS.
        os.link(temporary, destination)
        temporary.unlink()
        receipt = {
            "formatVersion": 1,
            "uuid": ARCHIVE_UUID,
            "encryptedArchive": destination.name,
            "sha256": sha256(destination),
            "sizeBytes": destination.stat().st_size,
            "sourceBytes": required,
            "restoredFiles": restored,
            "restoreVerified": True,
            "independentFileBytes": True,
        }
        with destination.with_suffix(destination.suffix + ".receipt.json").open("x") as stream:
            json.dump(receipt, stream, indent=2)
            stream.write("\n")
        return receipt
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()
        temporary.unlink(missing_ok=True)


def verify(encrypted, target, key):
    process = subprocess.Popen(
        gpg_args(key) + ["--decrypt", str(encrypted)], stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    seen = set()
    try:
        with tempfile.TemporaryDirectory(prefix=".restore-test-", dir=target) as temporary:
            with tarfile.open(fileobj=process.stdout, mode="r|gz") as archive:
                first = archive.next()
                if (
                    first is None
                    or first.name != "archive-manifest.json"
                    or not first.isfile()
                    or first.size > 16 * 1024**2
                ):
                    raise ValueError("Missing or invalid archive manifest")
                manifest = json.load(archive.extractfile(first))
                if manifest.get("formatVersion") != 1 or manifest.get("component") != "heteroes-encrypted-session":
                    raise ValueError("Unsupported archive manifest")
                while (entry := archive.next()) is not None:
                    name = PurePosixPath(entry.name)
                    if (
                        not entry.isfile()
                        or name.is_absolute()
                        or ".." in name.parts
                        or "\\" in entry.name
                        or name.as_posix() != entry.name
                        or entry.name in seen
                        or entry.name not in manifest["files"]
                    ):
                        raise ValueError("Unsafe or duplicate archive entry")
                    expected = manifest["files"][entry.name]
                    if entry.size != expected["sizeBytes"]:
                        raise ValueError("Archive size mismatch")
                    output = Path(temporary) / name
                    output.parent.mkdir(parents=True, exist_ok=True)
                    with archive.extractfile(entry) as stream, output.open("xb") as dest:
                        shutil.copyfileobj(stream, dest, 1024**2)
                    if sha256(output) != expected["sha256"]:
                        raise ValueError("Restored file checksum mismatch")
                    seen.add(entry.name)
            # Consume the entire ciphertext so GPG checks its integrity trailer.
            while process.stdout.read(1024**2):
                pass
            error = process.stderr.read()
            if process.wait():
                raise ValueError("Decryption integrity check failed: " + error.decode(errors="replace"))
            if seen != set(manifest["files"]):
                raise ValueError("Incomplete restored archive")
        return len(seen)
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--key", type=Path, required=True)
    parser.add_argument("--extra-file", type=Path, action="append", default=[])
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    check_destination(args.destination.parent)
    if args.verify_only and not args.key.is_file():
        parser.error("Existing recovery key is required")
    private_key(args.key)
    if args.verify_only:
        if not args.destination.is_file():
            parser.error("Archive does not exist")
        print(
            json.dumps(
                {"restoreVerified": True, "restoredFiles": verify(args.destination, args.destination.parent, args.key)}
            )
        )
    else:
        if args.source is None:
            parser.error("--source is required when creating an archive")
        print(json.dumps(create(args.source, args.destination, args.key, args.extra_file), indent=2))


if __name__ == "__main__":
    main()
