"""Relocate pure contracts and policies; split policy SQL and keep legacy validation HTTP errors at the API boundary."""
import ast
import copy
import json
from pathlib import Path
import re
import subprocess

root=Path('/home/pc5070ti/projects/heteroes');base='9d7d481b';proof=[]
def original(name):return subprocess.run(['git','show',f'{base}:backend/{name}.py'],cwd=root,check=True,capture_output=True,text=True).stdout
for name in ['config','addresses','request_models','monitor_models','throttle']:
 source=original(name);tree=ast.parse(source);expected=copy.deepcopy(tree)
 if name=='request_models':
  source=source.replace('from .policies import Strict','from .models import Strict')
  for n in expected.body:
   if isinstance(n,ast.ImportFrom) and n.module=='policies':n.module='models'
 assert ast.dump(expected,include_attributes=False)==ast.dump(ast.parse(source),include_attributes=False),name
 (root/f'backend/core/{name}.py').write_text(source)
 (root/f'backend/{name}.py').write_text('"""Compatibility namespace retained during core extraction."""\n\nimport sys\nfrom .core import '+name+' as _implementation\n\nsys.modules[__name__] = _implementation\n')
 if name=='request_models':
  shim=root/f'backend/{name}.py';text=shim.read_text().replace('sys.modules[__name__] = _implementation','from heteroes.catalog import DEFAULT_SCHEDULER_POLICY as DEFAULT_SCHEDULER_POLICY, SYNC_MODES as SYNC_MODES\n\nsys.modules[__name__] = _implementation');shim.write_text(text)
 proof.append({'module':name,'AST':'identical except Strict import where needed','bytesIdentical':name!='request_models'})
source=original('errors');runtime_class=next(n for n in ast.parse(source).body if isinstance(n,ast.ClassDef))
p=root/'backend/core/errors.py';p.write_text(p.read_text()+'\n\n'+ast.get_source_segment(source,runtime_class)+'\n')
(root/'backend/errors.py').write_text('"""Compatibility export for runtime admission errors."""\n\nfrom .core.errors import RuntimeRejected as RuntimeRejected\n')
proof.append({'class':'RuntimeRejected','AST':'identical'})
for name in ['policies','validation']:
 source=original(name);tree=ast.parse(source);raw=source.encode();starts=[0]
 for line in raw.splitlines(keepends=True):starts.append(starts[-1]+len(line))
 def span(n):return starts[n.lineno-1]+n.col_offset,starts[n.end_lineno-1]+n.end_col_offset
 changes={};queries=[];names=set()
 for function in [n for n in tree.body if isinstance(n,ast.FunctionDef)]:
  for n in ast.walk(function):
   if isinstance(n,ast.Name) and n.id=='HTTPException':changes[span(n)]=ast.Name(id='ServiceError',ctx=n.ctx)
   elif isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and isinstance(n.func.value,ast.Name) and n.func.value.id=='db' and n.func.attr=='execute':
    sql=ast.literal_eval(n.args[0]);table=re.search(r'(?i)\b(?:FROM|INTO|UPDATE)\s+([a-z_]+)',sql)
    stem=function.name+'_'+table[1].lower();query=stem;i=1
    while query in names:i+=1;query=stem+'_'+str(i)
    names.add(query);parameters=copy.deepcopy(n.args[1]) if len(n.args)>1 else ast.Tuple(elts=[],ctx=ast.Load())
    changes[span(n)]=ast.Call(func=ast.Attribute(value=ast.Name(id='repository',ctx=ast.Load()),attr=query,ctx=ast.Load()),args=[ast.Name(id='db',ctx=ast.Load()),parameters],keywords=[])
    queries.append((query,sql))
 for n in tree.body:
  if isinstance(n,ast.ImportFrom):
   if n.module=='fastapi':changes[span(n)]='from ..core.errors import ServiceError'
   elif n.level:
    new=copy.deepcopy(n)
    if new.module=='policies':new.level=1
    else:
     new.level+=1
     if new.module=='constants':new.module='core.constants'
    changes[span(n)]=ast.unparse(new)
 for (a,b),node in sorted(changes.items(),reverse=True):
  text=node if isinstance(node,str) else ast.unparse(ast.fix_missing_locations(node));raw=raw[:a]+text.encode()+raw[b:]
 service=raw.decode()
 if queries:service=service.replace('\n\n','\n\nfrom ..repositories.policies import PoliciesRepository as repository\n',1)
 class Expected(ast.NodeTransformer):
  def visit_Call(self,n):
   if span(n) in changes and not isinstance(changes[span(n)],str):return copy.deepcopy(changes[span(n)])
   return self.generic_visit(n)
  def visit_Name(self,n):return ast.Name(id='ServiceError',ctx=n.ctx) if n.id=='HTTPException' else n
 actual={n.name:n for n in ast.parse(service).body if isinstance(n,ast.FunctionDef)}
 for f in tree.body:
  if isinstance(f,ast.FunctionDef):assert ast.dump(Expected().visit(copy.deepcopy(f)),include_attributes=False)==ast.dump(actual[f.name],include_attributes=False),(name,f.name)
 assert len(queries)==(5 if name=='policies' else 0)
 (root/f'backend/services/{name}.py').write_text(service)
 if queries:
  repo='"""Shared product policy SQL."""\n\nfrom .base import execute\n\n\nclass PoliciesRepository:\n'
  for query,sql in queries:repo+='    @staticmethod\n    def '+query+'(db, parameters=()):\n        return execute(db, '+repr(sql)+', parameters)\n\n'
  (root/'backend/repositories/policies.py').write_text(repo)
 if name=='policies':
  (root/'backend/policies.py').write_text('"""Compatibility policy namespace retained during service extraction."""\n\nimport sys\nfrom .services import policies as _implementation\n\nsys.modules[__name__] = _implementation\n')
 else:
  f=copy.deepcopy(next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='validate_configuration'))
  call=ast.Call(func=ast.Name(id='_validate_configuration',ctx=ast.Load()),args=[ast.Name(id=a.arg,ctx=ast.Load()) for a in f.args.args],keywords=[ast.keyword(arg=a.arg,value=ast.Name(id=a.arg,ctx=ast.Load())) for a in f.args.kwonlyargs])
  f.body=[ast.Try(body=[ast.Return(value=call)],handlers=ast.parse('try:\n    pass\nexcept ServiceError as error:\n    raise HTTPException(error.status_code,error.detail,headers=error.headers) from None').body[0].handlers,orelse=[],finalbody=[])]
  api='"""Legacy validation HTTP boundary; configuration rules live in services."""\n\nfrom fastapi import HTTPException\nfrom ..core.errors import ServiceError\nfrom ..services.validation import validate_configuration as _validate_configuration\n\n'+ast.unparse(ast.fix_missing_locations(f))+'\n'
  (root/'backend/api/validation.py').write_text(api)
  (root/'backend/validation.py').write_text('"""Compatibility validation exports."""\n\nfrom .api.validation import validate_configuration as validate_configuration\nfrom .services.validation import freeze_python_code as freeze_python_code\n')
 proof.append({'module':name,'functions':len(actual),'sqlCalls':len(queries),'bodyAST':'same except repository forwarding/plain service error class','legacyValidationError':'HTTP boundary wrapper keeps old direct caller contract' if name=='validation' else None})
# Existing service domains now import shared policy business functions directly.
for p in (root/'backend/services').glob('*.py'):
 text=p.read_text();text=text.replace('from ..policies import','from .policies import');p.write_text(text)
(root/'.scratch/review-2026-11/B2/policies-validation-core-ast-proof.json').write_text(json.dumps({'base':base,'proof':proof},indent=2)+'\n')
print('Proved core contract moves, shared policy SQL and validation service/HTTP compatibility')
