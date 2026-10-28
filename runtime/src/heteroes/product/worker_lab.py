"""The Linux worker's plain JSON calls to the lab. Errors carry only the HTTP status, never URLs, tokens or text."""

import email.utils
import json
import subprocess
import time
import urllib.error
import urllib.request

from heteroes.http_transport import USER_AGENT
from .downloads import TRANSIENT

DEFAULT_LAB = "https://lab.heteroes.site"


def tailscale_ip(run=subprocess.run):
    try:
        shown = run(["tailscale", "ip", "-4"], capture_output=True, text=True, timeout=10)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    lines = shown.stdout.split()
    return lines[0] if shown.returncode == 0 and lines else None


class LabError(RuntimeError):
    def __init__(self, status):
        super().__init__(f"LAB_HTTP_{status}")
        self.status = status


def lab_request(server_url, path, token, body, method=None):
    """One JSON request to the lab. Errors carry only the status: never URLs, tokens or server text."""
    request = urllib.request.Request(
        server_url + path,
        data=None if body is None else json.dumps(body, allow_nan=False).encode(),
        method=method,
        headers={
            "Content-Type": "application/json",
            "User-Agent": USER_AGENT,
            **({"Authorization": "Bearer " + token} if token else {}),
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            data = response.read()
            return json.loads(data) if data else None
    except urllib.error.HTTPError as error:
        raise LabError(error.code) from None
    except TRANSIENT:
        raise RuntimeError("LAB_UNREACHABLE") from None


def lab_health(url, call=None):
    """The lab's health and, when the lab is reached directly, this machine's clock offset from it (seconds)."""
    if call:
        return call(url, "/api/v1/health", None, None), None
    request = urllib.request.Request(url + "/api/v1/health", headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            date = response.headers.get("Date")
            skew = time.time() - email.utils.parsedate_to_datetime(date).timestamp() if date else None
            return json.load(response), skew
    except urllib.error.HTTPError as error:
        raise LabError(error.code) from None
    except TRANSIENT:
        raise RuntimeError("LAB_UNREACHABLE") from None
