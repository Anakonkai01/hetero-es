"""SchedulingRepository SQL."""

from .base import execute


class SchedulingRepository:
    @staticmethod
    def _dispatch_once_select_queue(db, parameters=()):
        return execute(db, "SELECT run_id FROM queue ORDER BY sequence", parameters)

    @staticmethod
    def _dispatch_once_delete_queue(db, parameters=()):
        return execute(db, "DELETE FROM queue WHERE run_id=:p0", parameters)

    @staticmethod
    def _dispatch_run_update_experiments(db, parameters=()):
        return execute(db, "UPDATE experiments SET snapshot=:p0 WHERE id=:p1", parameters)

    @staticmethod
    def _dispatch_run_delete_queue(db, parameters=()):
        return execute(db, "DELETE FROM queue WHERE run_id=:p0", parameters)

    @staticmethod
    def _dispatch_run_delete_queue_2(db, parameters=()):
        return execute(db, "DELETE FROM queue WHERE run_id=:p0", parameters)

    @staticmethod
    def _dispatch_run_delete_queue_3(db, parameters=()):
        return execute(db, "DELETE FROM queue WHERE run_id=:p0", parameters)
