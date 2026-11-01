"""Move remaining operational SQL behind DB/repository owners and put CLI parsing in apps."""
import ast
import builtins
import copy
import json
from pathlib import Path
import subprocess

root=Path('/home/pc5070ti/projects/heteroes');base='9817afb5';proof=[];queries=[]
(root/'backend/apps').mkdir(exist_ok=True)
p=root/'backend/apps/__init__.py'
if not p.exists():p.write_text('"""Application composition and command entrypoints."""\n')
for domain in ['deployment','doctor','server']:
 source=subprocess.run(['git','show',f'{base}:backend/{domain}.py'],cwd=root,check=True,capture_output=True,text=True).stdout
 raw=source.encode();tree=ast.parse(source);starts=[0]
 for line in raw.splitlines(keepends=True):starts.append(starts[-1]+len(line))
 def span(n):return starts[n.lineno-1]+n.col_offset,starts[n.end_lineno-1]+n.end_col_offset
 changes={};sql_changes={};functions=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name!='main']
 for f in functions:
  for n in ast.walk(f):
   if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute):
    if isinstance(n.func.value,ast.Name) and n.func.value.id=='db' and n.func.attr=='execute':
     expr=n.args[0];free=sorted({v.id for v in ast.walk(expr) if isinstance(v,ast.Name) and isinstance(v.ctx,ast.Load)}-set(dir(builtins)))
     name=domain+'_'+f.name+'_'+str(len(queries)+1);parameters=copy.deepcopy(n.args[1]) if len(n.args)>1 else ast.Tuple(elts=[],ctx=ast.Load())
     sql_changes[span(n)]=ast.Call(func=ast.Attribute(value=ast.Name(id='repository',ctx=ast.Load()),attr=name,ctx=ast.Load()),args=[ast.Name(id='db',ctx=ast.Load()),parameters],keywords=[ast.keyword(arg=v,value=ast.Name(id=v,ctx=ast.Load())) for v in free])
     queries.append({'domain':domain,'name':name,'statement':ast.unparse(expr),'free':free})
    elif isinstance(n.func.value,ast.Name) and n.func.value.id=='sqlite3' and n.func.attr=='connect':
     new=copy.deepcopy(n);new.func=ast.Name(id='connect_readonly',ctx=ast.Load());sql_changes[span(n)]=new
   elif isinstance(n,ast.Attribute) and isinstance(n.value,ast.Name) and n.value.id=='sqlite3' and n.attr in ('Error','DatabaseError'):
    sql_changes[span(n)]=ast.Name(id='DatabaseError' if n.attr=='Error' else 'DatabaseCorruption',ctx=ast.Load())
 changes.update(sql_changes)
 for n in tree.body:
  if isinstance(n,ast.ImportFrom) and n.level:
   new=copy.deepcopy(n);new.level+=1
   if n.module=='policies':new.level=1
   elif n.module in ('config','addresses'):new.module='core.'+n.module
   elif n.module=='migrations':new.module='db.migrations'
   elif n.module=='local_storage':new.module='storage.local_backend'
   if n.module=='devices':changes[span(n)]='from .devices import AgentRuntime\nfrom ..core.device_models import Enrollment'
   else:changes[span(n)]=ast.unparse(new)
 main=next((n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='main'),None)
 if main:changes[span(main)]=''
 for n in tree.body:
  if isinstance(n,ast.If) and ast.unparse(n.test)=="__name__ == '__main__'":changes[span(n)]=''
 if domain=='server':
  contract=next(n for n in tree.body if isinstance(n,ast.ClassDef));assert contract.name=='Bootstrap'
  changes[span(contract)]=''
  core='"""Bootstrap input contract; secrets are never rendered as validation diagnostics."""\n\nfrom pydantic import BaseModel, ConfigDict, Field\n\n\n'+ast.get_source_segment(source,contract)+'\n'
  assert ast.dump(contract,include_attributes=False)==ast.dump(next(n for n in ast.parse(core).body if isinstance(n,ast.ClassDef)),include_attributes=False)
  (root/'backend/core/server_models.py').write_text(core)
 for (a,b),change in sorted(changes.items(),reverse=True):
  text=change if isinstance(change,str) else ast.unparse(ast.fix_missing_locations(change));raw=raw[:a]+text.encode()+raw[b:]
 service=raw.decode();header='from ..db.sqlite_diagnostics import SQLiteDiagnostics as repository, connect_readonly, DatabaseError, DatabaseCorruption\n'
 if domain=='server':header='from ..repositories.bootstrap import BootstrapRepository as repository\nfrom ..core.server_models import Bootstrap\n'
 first=ast.parse(service).body[0];lines=service.splitlines(keepends=True)
 position=first.end_lineno if isinstance(first,ast.Expr) and isinstance(first.value,ast.Constant) and isinstance(first.value.value,str) else 0
 lines.insert(position,'\n'+header);service=''.join(lines)
 class Expected(ast.NodeTransformer):
  def visit_Call(self,n):
   if span(n) in sql_changes:return copy.deepcopy(sql_changes[span(n)])
   return self.generic_visit(n)
  def visit_Attribute(self,n):
   if span(n) in sql_changes:return copy.deepcopy(sql_changes[span(n)])
   return self.generic_visit(n)
 actual={n.name:n for n in ast.parse(service).body if isinstance(n,ast.FunctionDef)}
 for f in functions:assert ast.dump(Expected().visit(copy.deepcopy(f)),include_attributes=False)==ast.dump(actual[f.name],include_attributes=False),(domain,f.name)
 target='bootstrap' if domain=='server' else domain
 (root/f'backend/services/{target}.py').write_text(service)
 if main:
  doc=ast.get_docstring(tree,clean=False)
  imports='import argparse\nfrom pathlib import Path\nimport sys\n'
  if domain=='doctor':imports+='from ..services.doctor import run_checks, FAIL\n'
  else:imports+='import json\nimport os\nimport signal\nimport threading\nfrom ..core.config import load_config\nfrom ..services.bootstrap import initialize\n'
  app=repr(doc)+'\n\n'+imports+'\n\n'+ast.get_source_segment(source,main)+'\n\nif __name__ == "__main__":\n    raise SystemExit(main())\n'
  assert ast.dump(main,include_attributes=False)==ast.dump(next(n for n in ast.parse(app).body if isinstance(n,ast.FunctionDef)),include_attributes=False)
  (root/f'backend/apps/{domain}.py').write_text(app)
 if domain=='doctor':
  shim='"""Compatibility doctor namespace and CLI during extraction."""\n\nimport sys\nfrom .services import doctor as _implementation\nfrom .apps.doctor import main\n\n_implementation.main = main\nif __name__ == "__main__":\n    raise SystemExit(main())\nelse:\n    sys.modules[__name__] = _implementation\n'
 elif domain=='deployment':shim='"""Compatibility deployment namespace during extraction."""\n\nimport sys\nfrom .services import deployment as _implementation\n\nsys.modules[__name__] = _implementation\n'
 else:shim='"""Compatibility packaged server exports and command entrypoint."""\n\nfrom .core.server_models import Bootstrap as Bootstrap\nfrom .services.bootstrap import initialize as initialize\nfrom .apps.server import main as main\n\nif __name__ == "__main__":\n    raise SystemExit(main())\n'
 (root/f'backend/{domain}.py').write_text(shim)
 proof.append({'domain':domain,'businessFunctionAST':'same except SQL/connection/driver-error forwarding','cliFunctionAST':'identical' if main else None,'sqlCalls':sum(q['domain']==domain for q in queries)})
for domain,name,path in [('diagnostics','SQLiteDiagnostics','backend/db/sqlite_diagnostics.py'),('server','BootstrapRepository','backend/repositories/bootstrap.py')]:
 prefix='"""SQLite operational diagnostics and driver boundary."""\n\nimport sqlite3\nfrom ..repositories.base import execute\n\nDatabaseError = sqlite3.Error\nDatabaseCorruption = sqlite3.DatabaseError\n\n\ndef connect_readonly(*args, **kwargs):\n    return sqlite3.connect(*args, **kwargs)\n\n\n' if domain=='diagnostics' else '"""Bootstrap admission persistence."""\n\nfrom .base import execute\n\n\n'
 text=prefix+'class '+name+':\n'
 for q in queries:
  if (q['domain']=='server') != (domain=='server'):continue
  extra=''.join(', '+v for v in q['free'])
  text+='    @staticmethod\n    def '+q['name']+'(db, parameters=()'+(', *'+extra if extra else '')+'):\n        return execute(db, '+q['statement']+', parameters)\n\n'
 ast.parse(text);(root/path).write_text(text)
assert len(queries)==8
(root/'.scratch/review-2026-11/B2/diagnostics-bootstrap-ast-proof.json').write_text(json.dumps({'base':base,'proof':proof,'queries':queries,'sqliteConnectionSemantics':'same sqlite3.connect arguments and original caller context-manager lifetime'},indent=2)+'\n')
print('Proved diagnostic/bootstrap bodies and CLI functions;',len(queries),'SQL calls relocated')
