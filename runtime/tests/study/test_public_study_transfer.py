"""A device without the private route (Tailscale off) fetches small dataset files over the lab's public HTTPS address;
large files and weights stay private-only, and every byte is still checked against the pinned SHA-256."""

import hashlib
import io
from types import SimpleNamespace

import pytest

from heteroes.study import prepare
from heteroes.study.prepare import PUBLIC_STUDY_LIMIT, transfer

DATA = b'{"rows": []}'
DIGEST = hashlib.sha256(DATA).hexdigest()
PRIVATE = "http://100.110.165.40:8002/api/v1/local-storage/private-token"
PUBLIC = "https://lab.example/api/v1/public-study/public-token"


def device(tmp_path, monkeypatch, grant):
    opened = []

    class Opener:
        def open(self, request, timeout):
            # the public edge refuses urllib's default agent: every download names the worker (finding 12)
            assert request.get_header("User-agent", "").startswith("HeteroES-Worker/")
            opened.append(request.full_url)
            return io.BytesIO(DATA)

    monkeypatch.setattr(prepare.urllib.request, "build_opener", lambda *a: Opener())
    agent = SimpleNamespace(call=lambda path, body: grant)
    return agent, opened


def fetch(agent, tmp_path, limit=10_000_000, reachable=False):
    assignment = {"assignmentId": "a" * 32, "epoch": 1}
    return transfer(agent, assignment, DIGEST, tmp_path / "d.json", limit, reachable=lambda url: reachable)


def test_the_public_link_is_used_only_when_the_private_route_does_not_answer(tmp_path, monkeypatch):
    agent, opened = device(tmp_path, monkeypatch, {"url": PRIVATE, "publicUrl": PUBLIC})
    assert fetch(agent, tmp_path).read_bytes() == DATA
    assert opened == [PUBLIC]
    (tmp_path / "d.json").unlink()
    fetch(agent, tmp_path, reachable=True)
    assert opened == [PUBLIC, PRIVATE]


def test_large_files_and_plain_http_public_links_never_go_public(tmp_path, monkeypatch):
    agent, opened = device(tmp_path, monkeypatch, {"url": PRIVATE, "publicUrl": PUBLIC})
    fetch(agent, tmp_path, limit=PUBLIC_STUDY_LIMIT + 1)  # weights: private only, whatever the lab offers
    assert opened == [PRIVATE]
    agent, opened = device(tmp_path, monkeypatch, {"url": PRIVATE, "publicUrl": PUBLIC.replace("https", "http")})
    (tmp_path / "d.json").unlink()
    with pytest.raises(ValueError, match="HTTPS"):
        fetch(agent, tmp_path)
    assert opened == []
