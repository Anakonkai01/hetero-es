"""Give metadata business policy, SQL, SQLite snapshots and filesystem publication their own layers."""
import ast
import copy
import json
from pathlib import Path
import subprocess

root=Path('/home/pc5070ti/projects/heteroes')
source=subprocess.run(['git','show','af048af2:backend/metadata_backup.py'],cwd=root,check=True,capture_output=True,text=True).stdout
tree=ast.parse(source);functions={n.name:n for n in tree.body if isinstance(n,ast.FunctionDef)}
create=functions['create_metadata_backup'];backup=next(n for n in create.body if isinstance(n,ast.With))
assert len(backup.items)==2 and len(backup.body)==1 and ast.unparse(backup.body[0])=='source.backup(destination)'
statement=next(n for n in ast.walk(create) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr=='execute')
assert ast.literal_eval(statement.args[0])=='INSERT OR REPLACE INTO settings VALUES (?,?)'
raw=source.encode();starts=[0]
for line in raw.splitlines(keepends=True):starts.append(starts[-1]+len(line))
def span(n):return starts[n.lineno-1]+n.col_offset,starts[n.end_lineno-1]+n.end_col_offset
sql_call=copy.deepcopy(statement);sql_call.func=ast.Attribute(value=ast.Name(id='repository',ctx=ast.Load()),attr='set_backup_status',ctx=ast.Load());sql_call.args=[ast.Name(id='db',ctx=ast.Load()),copy.deepcopy(statement.args[1])]
changes=[(*span(backup),b'backup_sqlite(store, database)'),(*span(statement),ast.unparse(ast.fix_missing_locations(sql_call)).encode()),(*span(functions['publish_new_directory']),b'')]
for a,b,text in sorted(changes,reverse=True):raw=raw[:a]+text+raw[b:]
service=raw.decode().replace('\n\n', '\n\nfrom ..db.backups import backup_sqlite\nfrom ..repositories.metadata import MetadataRepository as repository\n', 1)
actual={n.name:n for n in ast.parse(service).body if isinstance(n,ast.FunctionDef)}
class Rewrite(ast.NodeTransformer):
 def visit_With(self,node):
  if span(node)==span(backup):return ast.Expr(value=ast.Call(func=ast.Name(id='backup_sqlite',ctx=ast.Load()),args=[ast.Name(id='store',ctx=ast.Load()),ast.Name(id='database',ctx=ast.Load())],keywords=[]))
  return self.generic_visit(node)
 def visit_Call(self,node):
  if span(node)==span(statement):return copy.deepcopy(sql_call)
  return self.generic_visit(node)
for name in ['create_metadata_backup','backup_loop']:
 expected=Rewrite().visit(copy.deepcopy(functions[name]));assert ast.dump(expected,include_attributes=False)==ast.dump(actual[name],include_attributes=False),name
helper='"""Consistent SQLite snapshots; metadata publication policy belongs to services."""\n\nimport sqlite3\n\n\ndef backup_sqlite(store, database):\n'+ '\n'.join('    '+line for line in ast.unparse(backup).splitlines())+'\n'
assert ast.dump(next(n for n in ast.parse(helper).body if isinstance(n,ast.FunctionDef)).body[0],include_attributes=False)==ast.dump(backup,include_attributes=False)
filesystem='"""Atomic filesystem publication helpers."""\n\nimport ctypes\nimport os\nimport sys\n\n\n'+ast.get_source_segment(source,functions['publish_new_directory'])+'\n'
assert ast.dump(next(n for n in ast.parse(filesystem).body if isinstance(n,ast.FunctionDef)),include_attributes=False)==ast.dump(functions['publish_new_directory'],include_attributes=False)
repo='"""Metadata backup status SQL."""\n\nfrom .base import execute\n\n\nclass MetadataRepository:\n    @staticmethod\n    def set_backup_status(db, parameters):\n        return execute(db, "INSERT OR REPLACE INTO settings VALUES (?,?)", parameters)\n'
shim='"""Compatibility exports for metadata backup and atomic publication."""\n\nfrom .services.metadata_backup import create_metadata_backup as create_metadata_backup, backup_loop as backup_loop\nfrom .core.filesystem import publish_new_directory as publish_new_directory\n'
for file,text in [('backend/services/metadata_backup.py',service),('backend/db/backups.py',helper),('backend/core/filesystem.py',filesystem),('backend/repositories/metadata.py',repo),('backend/metadata_backup.py',shim)]:
 ast.parse(text);(root/file).write_text(text)
(root/'.scratch/review-2026-11/B2/metadata-backup-ast-proof.json').write_text(json.dumps({'base':'af048af2','serviceFunctionAST':'identical except snapshot helper and repository calls','databaseBackupBlockAST':'identical','atomicFilesystemFunctionAST':'identical','sqlCalls':1},indent=2)+'\n')
print('Proved metadata policy, exact SQLite snapshot block and atomic publication function')
