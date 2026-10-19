"""Platform operations: administrator-only routes, new GPU defaults, and the no-replace restore publication."""

import pytest

from backend.metadata_backup import publish_new_directory
from labkit import login


def test_platform_operations_are_denied_to_workspace_participant(setup):
    client, _, _ = setup
    participant = login(client, "participant")
    for method, path in [
        ("get", "/platform/operations"),
        ("get", "/platform/users"),
        ("post", "/platform/maintenance/resume"),
    ]:
        assert getattr(client, method)("/api/v1" + path, headers=participant).status_code == 403


def test_newly_configured_gpu_starts_unassigned_and_disabled(setup):
    _, store, runtime = setup
    store.ensure_workers(["5070ti", "3060", "new-gpu"])
    assert "new-gpu" not in store.assignments("lab")
    with store.db() as db:
        assert "new-gpu" in store.disabled_workers(db)
        assert db.execute('SELECT workspace_id FROM worker_assignments WHERE worker_id="new-gpu"').fetchone()[0] is None


def test_restore_publication_cannot_replace_existing_empty_directory(tmp_path):
    staging = tmp_path / "staging"
    staging.mkdir()
    (staging / "evidence").write_text("preserve")
    existing = tmp_path / "existing"
    existing.mkdir()
    with pytest.raises(FileExistsError):
        publish_new_directory(staging, existing)
    assert (staging / "evidence").read_text() == "preserve"
    assert list(existing.iterdir()) == []
