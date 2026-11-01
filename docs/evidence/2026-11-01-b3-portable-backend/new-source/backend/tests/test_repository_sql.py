"""Portable repository statements bind values, preserve JSON text and keep internal order out of public rows."""

from argon2 import PasswordHasher
import pytest

from backend.db.dialect import bind_list, json_text
from backend.core.errors import DatabaseConflict
from backend.repositories.history import HistoryRepository
from backend.repositories.inventory import InventoryRepository
from backend.repositories.notifications import NotificationsRepository
from backend.repositories.study_registry import StudyRegistryRepository
from backend.repositories.workspaces import WorkspacesRepository


def test_dynamic_placeholder_names_never_include_values():
    assert bind_list(["fixture", "quote'"], start=2) == ":p2,:p3"
    assert bind_list([]) == "NULL"


def test_json_projection_dynamic_filters_and_explicit_public_columns(database):
    owner, _ = database
    owner.initialize({}, PasswordHasher())
    with owner.transaction() as db:
        WorkspacesRepository.save_settings_insert_workspace_settings(
            db, ("lab", '{"defaultCoordinatorDeviceId":"fixture"}')
        )
        assert InventoryRepository.get_capabilities_select_workspace_settings(db, ("lab",)).fetchone()[0] == "fixture"
        assert (
            db.execute("SELECT " + json_text(db, "body", "absent") + " FROM workspace_settings").fetchone()[0] is None
        )
        for identifier in ("z-first", "a-second"):
            StudyRegistryRepository.save_insert_study_assets(db, (identifier, "lab", "owner", "dataset", "{}"))
        assert [row[0] for row in StudyRegistryRepository.list_select_study_assets(db, ("lab", "dataset"))] == [
            "{}",
            "{}",
        ]
        workspace = WorkspacesRepository.listed_workspaces_select_workspaces(db).fetchone()
        assert workspace.keys() == ["id", "name", "description", "creator"]
        with pytest.raises(DatabaseConflict):
            WorkspacesRepository.create_workspace_insert_workspaces(db, ("lab", "duplicate", "fixture", "owner"))
        WorkspacesRepository.create_workspace_insert_workspaces(db, ("after-conflict", "valid", "fixture", "owner"))
        assert WorkspacesRepository.ask_to_join_select_workspaces(db, ("after-conflict",)).fetchone()[0] == 1
        assert HistoryRepository.event_list_select_experiments(db, ("missing",), runs=["missing"]).fetchall() == []
        assert HistoryRepository.event_list_select_experiments(db, (), runs=[]).fetchall() == []
        assert HistoryRepository.event_list_select_monitoring_events(db, ("first", "second"), runs=[]).fetchall() == []
        assert NotificationsRepository.mark_read_update_notifications_2(db, (), numbers=[]).fetchone()[0] == 1
