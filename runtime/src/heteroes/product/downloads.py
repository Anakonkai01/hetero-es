"""Verified, resumable downloads of pinned files (name, url, sha256, sizeBytes) for the Linux worker."""

import hashlib
import http.client
from pathlib import Path
import socket
import sys
import time
import urllib.error
import urllib.request

from heteroes.http_transport import USER_AGENT


DOWNLOAD_ATTEMPTS = 6


TRANSIENT = (urllib.error.URLError, TimeoutError, ConnectionError, http.client.HTTPException, socket.timeout)


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


class Progress:
    """One line per download: redrawn in place on a terminal, every quarter otherwise (logs, pipes)."""

    def __init__(self, name, total, stream=None):
        self.name, self.total, self.stream = name, total, stream or sys.stderr
        self.tty = self.stream.isatty()
        self.started, self.shown, self.quarter = time.monotonic(), 0.0, 0

    def __call__(self, done):
        now = time.monotonic()
        rate = done / max(now - self.started, 1e-3) / 1e6
        line = f"  {self.name[:40]:40} {100 * done / self.total:5.1f}%  {done / 1e6:8.1f}/{self.total / 1e6:.1f} MB  {rate:6.1f} MB/s"
        if self.tty and (now - self.shown >= 0.2 or done >= self.total):
            self.stream.write("\r" + line + ("\n" if done >= self.total else ""))
            self.stream.flush()
            self.shown = now
        elif not self.tty and 4 * done // self.total > self.quarter:
            self.quarter = 4 * done // self.total
            print(line, file=self.stream, flush=True)


def _fetch(item, partial, progress):
    """Continue `partial` from where it stopped (HTTP Range); a server that ignores the range sends it all again."""
    offset = partial.stat().st_size if partial.exists() else 0
    if offset > item["sizeBytes"]:
        partial.unlink()
        offset = 0
    headers = {"User-Agent": USER_AGENT, **({"Range": f"bytes={offset}-"} if offset else {})}
    with urllib.request.urlopen(urllib.request.Request(item["url"], headers=headers), timeout=60) as response:
        if offset and getattr(response, "status", None) != 206:
            offset = 0
        with open(partial, "ab" if offset else "wb") as output:
            size = offset
            for block in iter(lambda: response.read(1 << 20), b""):
                size += len(block)
                if size > item["sizeBytes"]:
                    break
                output.write(block)
                if progress:
                    progress(size)


def verified_download(item, directory, say=print, attempts=DOWNLOAD_ATTEMPTS, sleep=time.sleep, progress=None):
    """Fetch `item` (name, url, sha256, sizeBytes) into `directory` once; a file that does not match is never kept.
    Network failures are retried with growing pauses and the download resumes where it stopped."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    target = directory / item["name"]
    if target.is_file() and target.stat().st_size == item["sizeBytes"] and sha256_file(target) == item["sha256"]:
        return target
    partial = target.with_name(target.name + ".part")
    say(f"downloading {item['name']} ({item['sizeBytes'] / 1e6:.1f} MB)")
    for attempt in range(1, attempts + 1):
        try:
            _fetch(item, partial, progress)
            break
        except urllib.error.HTTPError as error:
            if error.code < 500 or attempt == attempts:
                raise RuntimeError(f"DOWNLOAD_FAILED: {item['name']} (HTTP {error.code})") from None
        except TRANSIENT as error:
            if attempt == attempts:
                raise RuntimeError(f"DOWNLOAD_FAILED: {item['name']} ({type(error).__name__})") from None
        delay = min(60, 2**attempt)
        say(f"  network problem; retrying in {delay} s (attempt {attempt + 1} of {attempts})")
        sleep(delay)
    if partial.stat().st_size != item["sizeBytes"] or sha256_file(partial) != item["sha256"]:
        partial.unlink()
        raise RuntimeError("CHECKSUM_MISMATCH: " + item["name"])
    partial.rename(target)
    return target
