"""Inventory SQL; transaction ownership is separate."""

from ..db.dialect import json_text
from .base import execute


class InventoryRepository:
    @staticmethod
    def get_capabilities_select_workspace_settings(db, parameters=()):
        return execute(
            db,
            f"SELECT {json_text(db, 'body', 'defaultCoordinatorDeviceId')} FROM workspace_settings WHERE workspace_id=:p0",
            parameters,
        )

    @staticmethod
    def resources_select_memberships(db, parameters=()):
        return execute(
            db,
            "SELECT u.profile,m.role FROM memberships m JOIN users u ON u.id=m.user_id WHERE workspace_id=:p0",
            parameters,
        )
