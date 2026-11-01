"""Metadata payload naming is portable across the local and cloud database formats."""

import pytest

from backend.storage.local_backend import LocalBackend


@pytest.mark.parametrize("filename", ["product.sqlite", "product.pgdump"])
def test_local_metadata_storage_accepts_both_database_payload_formats(tmp_path, filename):
    backend = LocalBackend(
        tmp_path / "bulk", tmp_path / "key", "http://127.0.0.1:18052", metadata_root=tmp_path / "metadata"
    )
    key = "metadata/" + "a" * 32 + "/" + filename
    backend.put(key, b"private metadata payload")
    assert b"".join(backend.get(key)) == b"private metadata payload"
    assert (tmp_path / "metadata" / key).is_file() and not (tmp_path / "bulk" / key).exists()
