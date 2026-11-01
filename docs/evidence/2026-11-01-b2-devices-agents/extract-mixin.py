"""Move an agent business mixin with exact body proof and separate repository SQL."""
import ast
import builtins
import copy
import json
from pathlib import Path
import re
import subprocess
import sys

root=Path('/home/pc5070ti/projects/heteroes');name=sys.argv[1]
expected={'agent_commands':6,'agent_polling':30,'agent_scheduling':33};assert name in expected
source=subprocess.run(['git','show',f'96d662e7:backend/{name}.py'],cwd=root,check=True,capture_output=True,text=True).stdout
tree=ast.parse(source);klass=next(n for n in tree.body if isinstance(n,ast.ClassDef));repo_class=klass.name+'Repository'
raw=source.encode();starts=[0]
for line in raw.splitlines(keepends=True):starts.append(starts[-1]+len(line))
def span(n):return starts[n.lineno-1]+n.col_offset,starts[n.end_lineno-1]+n.end_col_offset
changes={};queries=[];count=0;uses_begin=False;names=set()
for method in klass.body:
 if not isinstance(method,ast.FunctionDef):continue
 for n in ast.walk(method):
  if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and isinstance(n.func.value,ast.Name) and n.func.value.id=='db' and n.func.attr=='execute':
   count+=1;expr=n.args[0]
   try:literal=ast.literal_eval(expr)
   except (ValueError,TypeError):literal=None
   if literal=='BEGIN IMMEDIATE':
    call=ast.Call(func=ast.Name(id='begin_write',ctx=ast.Load()),args=[ast.Name(id='db',ctx=ast.Load())],keywords=[]);uses_begin=True
   else:
    text=literal if literal is not None else ast.unparse(expr);verb=re.search(r'(?i)\b(SELECT|INSERT|UPDATE|DELETE|BEGIN)\b',text)
    verb=verb[1].lower() if verb else 'query';table=re.search(r'(?i)\b(?:FROM|INTO|UPDATE)\s+([a-z_]+)',text)
    stem=method.name+'_'+verb+'_'+(table[1].lower() if table else 'value');query=stem;i=1
    while query in names:i+=1;query=stem+'_'+str(i)
    assert query.isidentifier();names.add(query)
    free=sorted({v.id for v in ast.walk(expr) if isinstance(v,ast.Name) and isinstance(v.ctx,ast.Load)}-set(dir(builtins)))
    params=copy.deepcopy(n.args[1]) if len(n.args)>1 else ast.Tuple(elts=[],ctx=ast.Load())
    call=ast.Call(func=ast.Attribute(value=ast.Name(id='repository',ctx=ast.Load()),attr=query,ctx=ast.Load()),args=[ast.Name(id='db',ctx=ast.Load()),params],keywords=[ast.keyword(arg=v,value=ast.Name(id=v,ctx=ast.Load())) for v in free])
    queries.append({'method':query,'scope':method.name,'statement':ast.unparse(expr),'free':free})
   changes[span(n)]=call
  elif isinstance(n,ast.Name) and n.id=='HTTPException':changes[span(n)]=ast.Name(id='ServiceError',ctx=ast.Load())
assert count==expected[name],(name,count)
# Relative imports move up one package level; retain explicit compatibility exports.
for n in ast.walk(tree):
 if isinstance(n,ast.ImportFrom):
  if n.module=='fastapi':
   replacement='from ..core.errors import ServiceError\n'+f'from ..repositories.{name} import {repo_class} as repository'
   if uses_begin:replacement+='\nfrom ..db.transactions import begin_write'
   changes[span(n)]=replacement
  elif n.level:
   new=copy.deepcopy(n);new.level+=1
   if new.module=='migrations':new.module='db.migrations'
   for alias in new.names:
    if n in tree.body and alias.asname is None and alias.name!='*':alias.asname=alias.name
   changes[span(n)]=ast.unparse(new)
for (a,b),n in sorted(changes.items(),reverse=True):
 text=n if isinstance(n,str) else ast.unparse(ast.fix_missing_locations(n));raw=raw[:a]+text.encode()+raw[b:]
service=raw.decode();parsed=ast.parse(service);actual=next(n for n in parsed.body if isinstance(n,ast.ClassDef))
class Expected(ast.NodeTransformer):
 def visit_ImportFrom(self,n):
  if n.level:
   n=copy.deepcopy(n);n.level+=1
   if n.module=='migrations':n.module='db.migrations'
  return n
 def visit_Call(self,n):
  if span(n) in changes and not isinstance(changes[span(n)],str):return copy.deepcopy(changes[span(n)])
  return self.generic_visit(n)
 def visit_Name(self,n):
  if n.id=='HTTPException':return ast.Name(id='ServiceError',ctx=ast.Load())
  return n
normalized=Expected().visit(copy.deepcopy(klass));assert ast.dump(normalized,include_attributes=False)==ast.dump(actual,include_attributes=False),klass.name
repo='"""'+klass.name+' SQL; business decisions stay in the service mixin."""\n\nfrom .base import execute\n\n\nclass '+repo_class+':\n'
for q in queries:
 extra=''.join(', '+n for n in q['free'])
 repo+='    @staticmethod\n    def '+q['method']+'(db, parameters=()'+(', *'+extra if extra else '')+'):\n        return execute(db, '+q['statement']+', parameters)\n\n'
ast.parse(repo)
(root/f'backend/services/{name}.py').write_text(service);(root/f'backend/repositories/{name}.py').write_text(repo)
(root/f'backend/{name}.py').write_text('"""Compatibility module retained during the business-layer extraction."""\n\nimport sys\nfrom .services import '+name+' as _implementation\n\nsys.modules[__name__] = _implementation\n')
(root/f'.scratch/review-2026-11/B2/{name}-ast-proof.json').write_text(json.dumps({'module':name,'class':klass.name,'sqlCalls':count,'classBodyAST':'same except repository/write-boundary calls, plain service errors and relocated relative imports','methodSignatures':'identical','comments':'preserved by source-span edits','queries':queries},indent=2)+'\n')
print(name,':',count,'SQL calls separated; class body/signature proof passed')
