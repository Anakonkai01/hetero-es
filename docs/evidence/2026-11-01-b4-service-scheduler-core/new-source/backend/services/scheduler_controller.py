"""Run the local dispatcher or a PostgreSQL active/standby scheduler whose ticks use its owning session."""

import logging

from ..db.leadership import SchedulerLeader


class SchedulerController:
    def __init__(self, store, *, interval=1):
        if not 0 < interval <= 60:
            raise ValueError("Scheduler interval must be between zero and sixty seconds")
        self.store, self.interval = store, interval
        self.active, self._leader = False, None

    @property
    def backend_pid(self):
        return self._leader.backend_pid if self._leader is not None else None

    def run(self, stop):
        if self.store.database.dialect == "sqlite":
            self.store.dispatch(stop)
            return
        try:
            with SchedulerLeader(self.store.database) as leader:
                self._leader = leader
                while not stop.wait(self.interval):
                    try:
                        if not leader.try_acquire():
                            self.active = False
                            continue
                        self.active = True
                        # Keep the same operation-lock -> DB-lock ordering as an ordinary Store.dispatch_once.
                        with self.store.operation_lock, leader.session():
                            self.store.dispatch_once()
                    except Exception as error:
                        self.active = False
                        try:
                            self.store.last_error = type(error).__name__
                        except Exception:
                            logging.getLogger(__name__).warning("Scheduler diagnostic persistence unavailable")
                        logging.getLogger(__name__).warning("Scheduler tick failed: %s", type(error).__name__)
        finally:
            self.active, self._leader = False, None
