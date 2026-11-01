"""Export actual logical schema contracts from isolated SQLite and PostgreSQL instances."""
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import uuid

from argon2 import PasswordHasher
from sqlalchemy.engine import URL

root=Path('/home/pc5070ti/projects/heteroes');sys.path.insert(0,str(root));sys.path.insert(0,str(root/'backend/tests'))
from backend.db.engine import Database
from test_database_schema import _contract

scratch=Path(__file__).parent
private=json.loads((scratch/'postgres-private.json').read_text())
url=URL.create('postgresql+psycopg',username=private['username'],password=private['password'],host='127.0.0.1',port=private['port'],database=private['database'])
schema='schema_receipt_'+uuid.uuid4().hex
with Database(url) as administration:
 with administration.transaction() as db:db.execute('CREATE SCHEMA '+schema)
 try:
  with TemporaryDirectory(dir=scratch) as temporary, Database(Path(temporary)/'parity.sqlite') as sqlite, Database(url,connect_args={'options':'-csearch_path='+schema}) as postgres:
   sqlite.initialize({},PasswordHasher());postgres.initialize({},PasswordHasher())
   left,right=_contract(sqlite),_contract(postgres)
   assert left==right
   receipt={'equal':True,'tables':len(left),'columns':sum(len(t['columns']) for t in left.values()),'normalization':'SQLAlchemy logical type affinity; PK/unique column sets. SQLite TEXT PRIMARY KEY implicit nullability and identity/default mechanisms are deliberately dialect-specific; behavioral uniqueness/precision/order tests are separate.','sqlite':left,'postgresql':right}
   (scratch/'final-schema-parity.json').write_text(json.dumps(receipt,indent=2)+'\n')
   print('Actual schema parity:',receipt['tables'],'tables,',receipt['columns'],'columns')
 finally:
  with administration.transaction() as db:db.execute('DROP SCHEMA '+schema+' CASCADE')
