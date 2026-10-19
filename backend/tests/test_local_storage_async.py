"""Disk flushes and chunk writes must not stop the API event loop."""

import asyncio
import os
import threading
from urllib.parse import urlsplit
import httpx
import pytest
from fastapi import FastAPI
from backend.local_storage import LocalBackend


def setup(tmp_path):
    backend = LocalBackend(tmp_path / "objects", tmp_path / "private/key", "http://127.0.0.1:8002")
    app = FastAPI()
    backend.install_routes(app)

    @app.get("/health")
    async def health():
        return {"ok": True}

    entry = backend.upload_plan("uploads/" + "a" * 64 + "/" + "b" * 32, 7)
    return backend, app, urlsplit(entry["url"]).path


@pytest.mark.parametrize("operation", ["fsync", "write", "open"])
def test_slow_disk_operation_keeps_unrelated_health_request_responsive(tmp_path, monkeypatch, operation):
    backend, app, url = setup(tmp_path)
    entered = threading.Event()
    release = threading.Event()
    finished = threading.Event()
    from backend.local_storage import _Upload

    original = os.fsync if operation == "fsync" else getattr(_Upload, operation)

    def slow_operation(*args):
        entered.set()
        release.wait(2)
        result = original(*args)
        finished.set()
        return result

    monkeypatch.setattr(
        "backend.local_storage.os.fsync" if operation == "fsync" else "backend.local_storage._Upload." + operation,
        slow_operation,
    )

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            upload = asyncio.create_task(client.put(url, content=b"weights"))
            try:

                async def await_entry():
                    while not entered.is_set():
                        await asyncio.sleep(0.01)

                await asyncio.wait_for(await_entry(), 5)
                health = await asyncio.wait_for(client.get("/health"), 0.5)
                assert health.status_code == 200
                assert not finished.is_set(), "The health request ran only after disk IO unblocked the event loop"
            finally:
                release.set()
                response = await upload
            assert response.status_code == 200

    asyncio.run(scenario())
    assert backend.path("uploads/" + "a" * 64 + "/" + "b" * 32).read_bytes() == b"weights"


@pytest.mark.parametrize("content,status", [(b"short", 400), (b"oversized", 413)])
def test_failed_stream_cleans_partial_file_and_does_not_publish(tmp_path, content, status):
    backend, app, url = setup(tmp_path)

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.put(url, content=content, headers={"Content-Length": "7"})
            assert response.status_code == status

    asyncio.run(scenario())
    target = backend.path("uploads/" + "a" * 64 + "/" + "b" * 32)
    assert not target.exists() and list(target.parent.glob(".pending-*")) == []


def test_disconnected_stream_closes_and_removes_partial_upload(tmp_path):
    backend, app, url = setup(tmp_path)

    async def content():
        yield b"abc"
        raise RuntimeError("synthetic disconnect")

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            with pytest.raises(RuntimeError, match="synthetic disconnect"):
                await client.put(url, content=content(), headers={"Content-Length": "7"})

    asyncio.run(scenario())
    target = backend.path("uploads/" + "a" * 64 + "/" + "b" * 32)
    assert not target.exists() and list(target.parent.glob(".pending-*")) == []


def test_task_cancellation_during_fsync_waits_for_disk_ownership_before_close(tmp_path, monkeypatch):
    backend, app, url = setup(tmp_path)
    entered = threading.Event()
    release = threading.Event()
    finished = threading.Event()
    errors = []
    original = os.fsync

    def slow_fsync(fd):
        entered.set()
        release.wait(2)
        try:
            original(fd)
        except OSError as error:
            errors.append(type(error).__name__)
        finally:
            finished.set()

    monkeypatch.setattr("backend.local_storage.os.fsync", slow_fsync)

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            task = asyncio.create_task(client.put(url, content=b"weights"))
            while not entered.is_set():
                await asyncio.sleep(0.01)
            task.cancel()
            try:
                await asyncio.sleep(0.05)
                assert not finished.is_set(), "Cleanup blocked the event loop waiting for the disk worker"
            finally:
                release.set()
            with pytest.raises(asyncio.CancelledError):
                await task
            while not finished.is_set():
                await asyncio.sleep(0.01)

    asyncio.run(scenario())
    assert errors == [], "Cleanup closed a descriptor while the disk worker still owned it"
    target = backend.path("uploads/" + "a" * 64 + "/" + "b" * 32)
    assert list(target.parent.glob(".pending-*")) == []
    if target.exists():
        assert target.read_bytes() == b"weights"
