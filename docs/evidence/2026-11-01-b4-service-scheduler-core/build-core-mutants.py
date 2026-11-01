import json
from pathlib import Path
items=[
('all service processes register every product route','backend/apps/routing.py','return self.service == "all" or owner(method, path) == self.service','return True'),
('storage routes are assigned to the API','backend/apps/routing.py','if pair in _STORAGE:','if False:'),
('device routes are assigned to the API','backend/apps/routing.py','if pair in _DEVICES:','if False:'),
('included routers bypass service ownership','backend/apps/routing.py','return self.app.include_router(filtered, **options)','return self.app.include_router(router, **options)'),
('API processes start a scheduler loop','backend/apps/factory.py','if dispatch and service in {"all", "scheduler"}:','if dispatch:'),
('API processes start metadata backup loops','backend/apps/factory.py','if service in {"all", "storage"} and getattr(runtime, "storage_backend", None) is not None:','if getattr(runtime, "storage_backend", None) is not None:'),
('scheduler sessions return to a connection pool','backend/db/leadership.py','connection.detach()','pass'),
('heartbeats reacquire a recursive session lock','backend/db/leadership.py','''if self._held:
            return self.heartbeat()''','''if self._held:
            self._connection.scalar(text("SELECT pg_try_advisory_lock(:key)"), {"key": SCHEDULER_LOCK})
            self._connection.commit()
            return self.heartbeat()'''),
('graceful shutdown omits explicit unlock','backend/db/leadership.py','text("SELECT pg_advisory_unlock(:key)")','text("SELECT :key")'),
('scheduler and write locks collide','backend/db/leadership.py','SCHEDULER_LOCK = 0x4845534348454431','SCHEDULER_LOCK = 0x48455445524F4553'),
('bound business operations use a fresh pooled session','backend/db/engine.py','physical = getattr(self._local, "session", None)','physical = None'),
('one failed job rolls back the whole scheduler tick','backend/services/scheduler_controller.py','leader.session()','leader.transaction()'),
('cloud scheduler diagnostics become local memory','backend/services/cluster_state.py','return self.store.database.dialect == "postgresql"','return False'),
('conflicting configured cluster identities are accepted','backend/services/cluster_state.py','if configured is not None and configured != identifier:','if False:'),
('scheduler failure is immediately erased','backend/services/cluster_state.py','repository.write(db, "schedulerLastError", json.dumps(value))','repository.write(db, "schedulerLastError", json.dumps(None))'),
('standby session reports leadership without acquiring','backend/db/leadership.py','self._held, self.backend_pid = bool(held), identity','self._held, self.backend_pid = True, identity'),
]
mutants=[dict(name=n,file=f,old=o,new=v) for n,f,o,v in items]
for item in mutants:assert Path(item['file']).read_text().count(item['old'])==1,(item['name'],Path(item['file']).read_text().count(item['old']))
Path('.scratch/review-2026-11/B4/core-mutants.json').write_text(json.dumps(mutants,indent=2)+'\n')
