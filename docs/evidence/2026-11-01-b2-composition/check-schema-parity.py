"""Recreate a full isolated product schema and compare every catalog/column/index record with B1."""
import hashlib
import json
from pathlib import Path
import tempfile

from backend.apps.factory import create_app
from backend.services.devices import AgentRuntime
from backend.storage.local_backend import LocalBackend

root=Path('/home/pc5070ti/projects/heteroes');baseline=root/'.scratch/review-2026-11/B1/schema-before.json'
expected=json.loads(baseline.read_text())
with tempfile.TemporaryDirectory(prefix='heteroes-b2-schema-') as temporary:
    work=Path(temporary)
    backend=LocalBackend(work/'objects',work/'signing.key','http://127.0.0.1:18052')
    app=create_app(work/'product.sqlite',{'admin':'isolated-schema-fixture-password'},AgentRuntime(backend),dispatch=False)
    with app.state.store.db() as db:
        catalog=[dict(row) for row in db.execute("SELECT type,name,tbl_name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' ORDER BY type,name")]
        tables={row['name']:{'columns':[dict(c) for c in db.execute('PRAGMA table_info("'+row['name']+'")')],'indexes':[dict(i) for i in db.execute('PRAGMA index_list("'+row['name']+'")')]} for row in catalog if row['type']=='table'}
    actual={'catalog':catalog,'tables':tables}
    assert actual==expected,{'catalogEqual':catalog==expected['catalog'],'tableNamesEqual':set(tables)==set(expected['tables'])}
receipt={'baselineSha256':hashlib.sha256(baseline.read_bytes()).hexdigest(),'tables':len(tables),'columns':sum(len(t['columns']) for t in tables.values()),'catalogColumnsIndexes':'byte-equivalent JSON values','result':'PASS','scope':'new isolated SQLite database; no live lab inspected'}
(root/'.scratch/review-2026-11/B2/schema-parity.json').write_text(json.dumps(receipt,indent=2)+'\n')
print(json.dumps(receipt,indent=2))
