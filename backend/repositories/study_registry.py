"""Study_Registry SQL; transaction ownership is separate."""

from .base import execute


class StudyRegistryRepository:
    @staticmethod
    def set_dataset_limits_insert_settings(db, parameters=()):
        return execute(
            db,
            "INSERT INTO settings(key,value)  VALUES ('datasetLimits', :p0) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            parameters,
        )

    @staticmethod
    def upload_plan_insert_study_uploads(db, parameters=()):
        return execute(
            db,
            "INSERT INTO study_uploads(id,asset_id,name,object_sha,upload_key,size)  VALUES (:p0,:p1,:p2,:p3,:p4,:p5)",
            parameters,
        )

    @staticmethod
    def publish_update_study_assets(db, parameters=()):
        return execute(db, "UPDATE study_assets SET body=:p0 WHERE id=:p1", parameters)

    @staticmethod
    def publish_select_study_uploads(db, parameters=()):
        return execute(
            db,
            "SELECT id,asset_id,name,object_sha,upload_key,size FROM study_uploads WHERE asset_id=:p0 AND name=:p1 ORDER BY _insert_order DESC",
            parameters,
        )

    @staticmethod
    def transfer_select_assignments(db, parameters=()):
        return execute(
            db,
            "SELECT id,run_id,coordinator,epoch,body,snapshot,released FROM assignments WHERE id=:p0 AND epoch=:p1 AND released=0",
            parameters,
        )

    @staticmethod
    def dataset_limits_select_settings(db, parameters=()):
        return execute(db, "SELECT value FROM settings WHERE key='datasetLimits'", parameters)

    @staticmethod
    def save_insert_study_assets(db, parameters=()):
        return execute(
            db, "INSERT INTO study_assets(id,workspace_id,owner,kind,body)  VALUES (:p0,:p1,:p2,:p3,:p4)", parameters
        )

    @staticmethod
    def list_select_study_assets(db, parameters=()):
        return execute(
            db, "SELECT body FROM study_assets WHERE workspace_id=:p0 AND kind=:p1 ORDER BY _insert_order", parameters
        )

    @staticmethod
    def get_select_study_assets(db, parameters=()):
        return execute(db, "SELECT body FROM study_assets WHERE id=:p0 AND workspace_id=:p1 AND kind=:p2", parameters)
