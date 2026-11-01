import ast,json
from pathlib import Path
p=Path('backend/db/postgres_backup.py');text=p.read_text();node=next(n for n in ast.parse(text).body if isinstance(n,ast.FunctionDef) and n.name=='_empty');empty=ast.get_source_segment(text,node)
items=[
('snapshot uses the wrong archive format','backend/db/postgres_backup.py','"--format=custom"','"--format=plain"'),
('client major version is not checked','backend/db/postgres_backup.py','if not re.search(r"\\(PostgreSQL\\)\\s+17(?:\\.|$)", version):','if False:'),
('ambient libpq service configuration survives','backend/db/postgres_backup.py','environment = {key: value for key, value in os.environ.items() if not key.startswith("PG")}','environment = dict(os.environ)'),
('restore checksum and manifest validation is omitted','backend/db/postgres_backup.py','    _verify(source, manifest)\n','    pass\n'),
('user pgx schemas are mistaken for system schemas','backend/db/postgres_backup.py',"left(n.nspname,3) <> 'pg_'","n.nspname NOT LIKE 'pg_%'"),
('nonempty restore targets are accepted','backend/db/postgres_backup.py',empty,'def _empty(database):\n    return True'),
('restore data and quarantine commit separately','backend/db/postgres_backup.py','"--single-transaction",',''),
('psql reports success after a restore validation error','backend/db/postgres_backup.py','"--set=ON_ERROR_STOP=1"','"--set=ON_ERROR_STOP=0"'),
('restored browser sessions remain valid','backend/db/postgres_backup.py','DELETE FROM sessions;','SELECT 1;'),
('restored unknown GPU ownership is erased','backend/db/postgres_backup.py','DELETE FROM cloud_downloads;','DELETE FROM cloud_downloads;\nDELETE FROM device_reservations;'),
('restored dispatch is opened immediately','backend/db/postgres_backup.py',"VALUES ('dispatchHold','true')","VALUES ('dispatchHold','false')"),
('uploaded metadata content is never verified','backend/services/metadata_backup.py','if size != size_bytes or check.hexdigest() != sha:','if False:'),
('failed cloud backup removes its local copy','backend/services/metadata_backup.py','except Exception as error:\n        status = {','except Exception as error:\n        database.unlink()\n        status = {'),
('retention deletes only SQLite payloads','backend/services/metadata_backup.py','storage.backend.delete(old_manifest["objectKey"])','storage.backend.delete("metadata/" + old.name + "/product.sqlite")'),
('metadata cloud quota is ignored','backend/services/metadata_backup.py','if usage["observedBytes"] + usage["reservedBytes"] + size_bytes + len(json.dumps(manifest)) > storage.quota:','if False:'),
('private tool stderr is exposed in an exception','backend/db/postgres_backup.py','raise PostgresBackupError("PostgreSQL metadata tool failed")','raise PostgresBackupError(completed.stderr)'),
]
mutants=[dict(name=n,file=f,old=o,new=v) for n,f,o,v in items]
for item in mutants:assert Path(item['file']).read_text().count(item['old'])==1,(item['name'],Path(item['file']).read_text().count(item['old']))
Path('.scratch/review-2026-11/B4/backup-mutants.json').write_text(json.dumps(mutants,indent=2)+'\n')
