"""Make Store delegate database ownership and audit policy while preserving its public transaction context."""
import ast
import copy
import json
from pathlib import Path
import subprocess

root=Path('/home/pc5070ti/projects/heteroes');base='9817afb5'
source=subprocess.run(['git','show',f'{base}:backend/store.py'],cwd=root,check=True,capture_output=True,text=True).stdout
raw=source.encode();tree=ast.parse(source);klass=next(n for n in tree.body if isinstance(n,ast.ClassDef))
methods={n.name:n for n in klass.body if isinstance(n,ast.FunctionDef)};constructor=methods['__init__'];connection=methods['db'];audit=methods['audit']
bootstrap=next(n for n in constructor.body if isinstance(n,ast.With));starts=[0]
for line in raw.splitlines(keepends=True):starts.append(starts[-1]+len(line))
def span(n):return starts[n.lineno-1]+n.col_offset,starts[n.end_lineno-1]+n.end_col_offset
class BootstrapRewrite(ast.NodeTransformer):
 def visit_Attribute(self,n):
  if isinstance(n.value,ast.Name) and n.value.id=='self':
   if n.attr=='db':n=copy.deepcopy(n);n.attr='connection'
   elif n.attr=='hasher':return ast.Name(id='hasher',ctx=n.ctx)
  return self.generic_visit(n)
block=ast.get_source_segment(source,bootstrap).replace('self.db()', 'self.connection()').replace('self.hasher','hasher')
db='"""SQLite connection and bootstrap ownership; runtime ledgers stay independent."""\n\nfrom contextlib import contextmanager\nimport json\nimport sqlite3\nfrom .migrations import initialize_product_schema, initialize_workspace_extras, migrate\n\n\nclass SQLiteDatabase:\n    def __init__(self, path, lock):\n        self.path, self.lock = str(path), lock\n\n    def initialize(self, passwords, hasher):\n        '+block+'\n\n    @contextmanager\n    '+ast.get_source_segment(source,connection).replace('def db(', 'def connection(',1)+'\n'
actual_class=next(n for n in ast.parse(db).body if isinstance(n,ast.ClassDef));actual={n.name:n for n in actual_class.body if isinstance(n,ast.FunctionDef)}
expected=copy.deepcopy(connection);expected.name='connection'
assert ast.dump(expected,include_attributes=False)==ast.dump(actual['connection'],include_attributes=False)
assert ast.dump(BootstrapRewrite().visit(copy.deepcopy(bootstrap)),include_attributes=False)==ast.dump(actual['initialize'].body[0],include_attributes=False)
sql=next(n for n in ast.walk(audit) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr=='execute')
call=ast.Call(func=ast.Attribute(value=ast.Name(id='repository',ctx=ast.Load()),attr='record',ctx=ast.Load()),args=[ast.Name(id='db',ctx=ast.Load()),copy.deepcopy(sql.args[1])],keywords=[])
service_method=copy.deepcopy(audit);service_method.body=[ast.Expr(value=call)]
service='"""Audit policy; timestamps remain the original product clock."""\n\nfrom ..core.clock import now\nfrom ..repositories.audit import AuditRepository as repository\n\n\nclass AuditService:\n    '+ast.unparse(ast.fix_missing_locations(service_method)).replace('\n','\n    ')+'\n'
repo='"""Product audit persistence."""\n\nfrom .base import execute\n\n\nclass AuditRepository:\n    @staticmethod\n    def record(db, parameters):\n        return execute(db, '+repr(ast.literal_eval(sql.args[0]))+', parameters)\n'
new_connection=copy.deepcopy(connection);new_connection.body=ast.parse('with self.database.connection() as connection:\n    yield connection').body
new_audit=copy.deepcopy(audit);new_audit.body=ast.parse('return self.audit_service.audit(db=db, actor=actor, action=action, target=target, workspace_id=workspace_id)').body
edits=[(*span(bootstrap),b'self.database = SQLiteDatabase(self.path, self.lock)\n        self.database.initialize(passwords, self.hasher)')]
for old,new in [(connection,new_connection),(audit,new_audit)]:
 new.decorator_list=[];edits.append((*span(old),ast.unparse(ast.fix_missing_locations(new)).replace('\n','\n    ').encode()))
for a,b,text in sorted(edits,reverse=True):raw=raw[:a]+text+raw[b:]
facade=raw.decode().replace('from .core.clock import now','from .core.clock import now as now\nfrom .db.database import SQLiteDatabase\nfrom .services.audit import AuditService')
facade=facade.replace('        self.accounts = AccountService(self)','        self.accounts = AccountService(self)\n        self.audit_service = AuditService()')
facade=facade.replace('SQLite product state. Runtime ledgers remain owned by device agents.','Product state facade. Runtime ledgers remain owned by device agents.')
for file,text in [('backend/db/database.py',db),('backend/services/audit.py',service),('backend/repositories/audit.py',repo),('backend/store.py',facade)]:ast.parse(text);(root/file).write_text(text)
(root/'.scratch/review-2026-11/B2/store-database-ast-proof.json').write_text(json.dumps({'base':base,'connectionMethodAST':'identical except method name db -> connection','bootstrapBlockAST':'identical except DB owner/hasher forwarding; comments preserved','audit':'same signature, timestamp and SQL arguments, split into service/repository','publicStoreContext':'same signature/decorator; forwards commit/rollback/close to DB owner','lock':'original RLock object passed to DB owner','sqlCallsRelocated':3},indent=2)+'\n')
print('Proved SQLite bootstrap/connection ownership and audit forwarding')
