"""Run the local dispatcher or a PostgreSQL active/standby scheduler whose ticks use its owning session."""

import logging
import threading

from ..db.leadership import SchedulerLeader


class SchedulerController:
    def __init__(self, store, *, interval=1):
        if not 0 < interval <= 60:
            raise ValueError("Scheduler interval must be between zero and sixty seconds")
        self.store, self.interval = store, interval
        self._operation_lock = getattr(store, "operation_lock", threading.RLock())
        self.active, self._leader = False, None

    @property
    def backend_pid(self):
        return self._leader.backend_pid if self._leader is not None else None

    def run(self, stop):
        if self.store.database.dialect == "sqlite":
            self.active = True
            try:
                self.store.dispatch(stop)
            finally:
                with self._operation_lock:
                    self.active = False
            return
        leader = SchedulerLeader(self.store.database)
        self._leader = leader
        try:
            while not stop.wait(self.interval):
                try:
                    # Keep the same operation-lock -> DB-lock ordering as an ordinary Store.dispatch_once.
                    with self._operation_lock:
                        if not leader.try_acquire():
                            self.active = False
                            continue
                        self.active = True
                        with leader.session():
                            self.store.dispatch_once()
                except Exception as error:
                    self.active = False
                    try:
                        self.store.last_error = type(error).__name__
                    except Exception:
                        logging.getLogger(__name__).warning("Scheduler diagnostic persistence unavailable")
                    logging.getLogger(__name__).warning("Scheduler tick failed: %s", type(error).__name__)
        finally:
            with self._operation_lock:
                self.active, self._leader = False, None
                leader.close()

    def read_metrics(self, read):
        """A scrape cannot acquire leadership, reconnect as an old leader or race its owning session's tick."""
        with self._operation_lock:
            if not self.active:
                return None
            if self.store.database.dialect == "sqlite":
                return read()
            if self._leader is None:
                self.active = False
                return None
            try:
                with self._leader.session():
                    return read()
            except Exception:
                self.active = False
                return None
