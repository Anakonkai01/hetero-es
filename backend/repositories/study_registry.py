"""Study_Registry SQL; transaction ownership is separate."""

from .base import execute


class StudyRegistryRepository:
    @staticmethod
    def set_dataset_limits_insert_settings(db, parameters=()):
        return execute(db, "INSERT OR REPLACE INTO settings VALUES ('datasetLimits', ?)", parameters)

    @staticmethod
    def upload_plan_insert_study_uploads(db, parameters=()):
        return execute(db, "INSERT INTO study_uploads VALUES (?,?,?,?,?,?)", parameters)

    @staticmethod
    def publish_update_study_assets(db, parameters=()):
        return execute(db, "UPDATE study_assets SET body=? WHERE id=?", parameters)

    @staticmethod
    def publish_select_study_uploads(db, parameters=()):
        return execute(db, "SELECT * FROM study_uploads WHERE asset_id=? AND name=? ORDER BY rowid DESC", parameters)

    @staticmethod
    def transfer_select_assignments(db, parameters=()):
        return execute(db, "SELECT * FROM assignments WHERE id=? AND epoch=? AND released=0", parameters)

    @staticmethod
    def dataset_limits_select_settings(db, parameters=()):
        return execute(db, "SELECT value FROM settings WHERE key='datasetLimits'", parameters)

    @staticmethod
    def save_insert_study_assets(db, parameters=()):
        return execute(db, "INSERT INTO study_assets VALUES (?,?,?,?,?)", parameters)

    @staticmethod
    def list_select_study_assets(db, parameters=()):
        return execute(db, "SELECT body FROM study_assets WHERE workspace_id=? AND kind=? ORDER BY rowid", parameters)

    @staticmethod
    def get_select_study_assets(db, parameters=()):
        return execute(db, "SELECT body FROM study_assets WHERE id=? AND workspace_id=? AND kind=?", parameters)
