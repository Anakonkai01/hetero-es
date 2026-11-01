"""Recovery_Storage SQL; transaction ownership is separate."""

from .base import execute


class RecoveryStorageRepository:
    @staticmethod
    def grant_select_assignments(db, parameters=()):
        return execute(db, "SELECT coordinator,epoch,run_id FROM assignments WHERE id=?", parameters)

    @staticmethod
    def point_run_select_recovery_points(db, parameters=()):
        return execute(db, "SELECT run_id FROM recovery_points WHERE id=?", parameters)

    @staticmethod
    def device_status_select_assignments(db, parameters=()):
        return execute(db, "SELECT coordinator FROM assignments WHERE run_id=? ORDER BY epoch DESC LIMIT 1", parameters)

    @staticmethod
    def historical_select_assignments(db, parameters=()):
        return execute(db, "SELECT 1 FROM assignments WHERE run_id=?", parameters)

    @staticmethod
    def ticket_insert_cloud_downloads(db, parameters=()):
        return execute(db, "INSERT INTO cloud_downloads VALUES (?,?,?,?,?,?)", parameters)

    @staticmethod
    def consume_delete_cloud_downloads(db, parameters=()):
        return execute(db, "DELETE FROM cloud_downloads WHERE digest=?", parameters)

    @staticmethod
    def consume_select_cloud_downloads(db, parameters=()):
        return execute(db, "SELECT * FROM cloud_downloads WHERE digest=? AND expires>?", parameters)

    @staticmethod
    def consume_select_memberships(db, parameters=()):
        return execute(db, "SELECT role FROM memberships WHERE workspace_id=? AND user_id=?", parameters)

    @staticmethod
    def consume_select_sessions(db, parameters=()):
        return execute(db, "SELECT 1 FROM sessions WHERE digest=? AND user_id=? AND expires>?", parameters)

    @staticmethod
    def begin_insert_recovery_points(db, parameters=()):
        return execute(db, "INSERT OR IGNORE INTO recovery_points VALUES (?,?,?,?,?,?,NULL,?)", parameters)

    @staticmethod
    def complete_object_update_cloud_objects(db, parameters=()):
        return execute(db, 'UPDATE cloud_objects SET status="UPLOADED" WHERE sha=?', parameters)

    @staticmethod
    def delete_point_delete_cloud_refs(db, parameters=()):
        return execute(db, "DELETE FROM cloud_refs WHERE point_id=?", parameters)

    @staticmethod
    def delete_point_delete_recovery_points(db, parameters=()):
        return execute(db, "DELETE FROM recovery_points WHERE id=?", parameters)

    @staticmethod
    def begin_insert_cloud_objects(db, parameters=()):
        return execute(db, 'INSERT OR IGNORE INTO cloud_objects VALUES (?,?,"PENDING",NULL,NULL)', parameters)

    @staticmethod
    def begin_insert_cloud_refs(db, parameters=()):
        return execute(db, "INSERT OR IGNORE INTO cloud_refs VALUES (?,?)", parameters)

    @staticmethod
    def verify_update_recovery_points(db, parameters=()):
        return execute(db, 'UPDATE recovery_points SET status="READY",error=NULL WHERE id=?', parameters)

    @staticmethod
    def points_select_recovery_points(db, parameters=()):
        return execute(
            db, "SELECT * FROM recovery_points WHERE run_id=? ORDER BY generation DESC,created DESC", parameters
        )

    @staticmethod
    def manifest_select_recovery_points(db, parameters=()):
        return execute(db, "SELECT manifest,status FROM recovery_points WHERE id=?", parameters)

    @staticmethod
    def delete_point_delete_cloud_objects(db, parameters=()):
        return execute(db, "DELETE FROM cloud_objects WHERE sha=?", parameters)

    @staticmethod
    def begin_select_recovery_points(db, parameters=()):
        return execute(db, "SELECT manifest,status FROM recovery_points WHERE id=?", parameters)

    @staticmethod
    def begin_select_cloud_objects(db, parameters=()):
        return execute(db, "SELECT * FROM cloud_objects", parameters)

    @staticmethod
    def begin_update_cloud_objects(db, parameters=()):
        return execute(db, "UPDATE cloud_objects SET upload_plan=?,expires=? WHERE sha=?", parameters)

    @staticmethod
    def complete_object_select_cloud_objects(db, parameters=()):
        return execute(
            db,
            "SELECT o.* FROM cloud_objects o JOIN cloud_refs r ON o.sha=r.sha WHERE r.point_id=? AND o.sha=?",
            parameters,
        )

    @staticmethod
    def verify_select_recovery_points(db, parameters=()):
        return execute(db, "SELECT * FROM recovery_points WHERE id=?", parameters)

    @staticmethod
    def verify_update_cloud_objects(db, parameters=()):
        return execute(
            db, 'UPDATE cloud_objects SET status="READY",upload_plan=NULL,expires=NULL WHERE sha=?', parameters
        )

    @staticmethod
    def verify_update_recovery_points_2(db, parameters=()):
        return execute(db, "UPDATE recovery_points SET status=?,error=? WHERE id=?", parameters)

    @staticmethod
    def delete_point_select_cloud_objects(db, parameters=()):
        return execute(
            db,
            "SELECT * FROM cloud_objects o WHERE NOT EXISTS(SELECT 1 FROM cloud_refs r WHERE r.sha=o.sha)",
            parameters,
        )

    @staticmethod
    def usage_select_cloud_objects(db, parameters=()):
        return execute(db, 'SELECT coalesce(sum(size),0) FROM cloud_objects WHERE status!="READY"', parameters)

    @staticmethod
    def begin_select_cloud_objects_2(db, parameters=()):
        return execute(db, "SELECT * FROM cloud_objects WHERE sha=?", parameters)

    @staticmethod
    def verify_update_cloud_objects_2(db, parameters=()):
        return execute(
            db, 'UPDATE cloud_objects SET status="PENDING",upload_plan=NULL,expires=NULL WHERE sha=?', parameters
        )

    @staticmethod
    def verify_select_cloud_objects(db, parameters=()):
        return execute(db, "SELECT * FROM cloud_objects WHERE sha=?", parameters)
