"""Make Store delegate device/scheduler business methods, with normalized body/signature proof."""
import ast
import builtins
import copy
import json
from pathlib import Path
import re
import subprocess

root=Path('/home/pc5070ti/projects/heteroes')
source=subprocess.run(['git','show','96d662e7:backend/store.py'],cwd=root,check=True,capture_output=True,text=True).stdout
tree=ast.parse(source);klass=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='Store')
domains={n:'device_state' for n in ['ensure_workers','assignments','disabled_workers','device_names','device_identities']}
domains.update({n:'scheduling' for n in ['dispatch_once','_dispatch_once','_dispatch_run','dispatch']})
methods=[n for n in klass.body if isinstance(n,ast.FunctionDef) and n.name in domains]
raw=source.encode();starts=[0]
for line in raw.splitlines(keepends=True):starts.append(starts[-1]+len(line))
def span(n):return starts[n.lineno-1]+n.col_offset,starts[n.end_lineno-1]+n.end_col_offset
sql={};queries={'device_state':[],'scheduling':[]};names=set();transaction=set()
for f in methods:
 for n in ast.walk(f):
  if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and isinstance(n.func.value,ast.Name) and n.func.value.id=='db' and n.func.attr=='execute':
   expr=n.args[0]
   try:literal=ast.literal_eval(expr)
   except (ValueError,TypeError):literal=None
   if literal=='BEGIN IMMEDIATE':
    sql[span(n)]=ast.Call(func=ast.Name(id='begin_write',ctx=ast.Load()),args=[ast.Name(id='db',ctx=ast.Load())],keywords=[]);transaction.add(domains[f.name]);continue
   text=literal if literal is not None else ast.unparse(expr);verb=re.search(r'(?i)\b(SELECT|INSERT|UPDATE|DELETE|BEGIN)\b',text)[1].lower();table=re.search(r'(?i)\b(?:FROM|INTO|UPDATE)\s+([a-z_]+)',text)
   stem=f.name+'_'+verb+'_'+(table[1].lower() if table else 'value');name=stem;i=1
   while name in names:i+=1;name=stem+'_'+str(i)
   names.add(name);free=sorted({v.id for v in ast.walk(expr) if isinstance(v,ast.Name) and isinstance(v.ctx,ast.Load)}-set(dir(builtins)))
   params=copy.deepcopy(n.args[1]) if len(n.args)>1 else ast.Tuple(elts=[],ctx=ast.Load())
   sql[span(n)]=ast.Call(func=ast.Attribute(value=ast.Name(id='repository',ctx=ast.Load()),attr=name,ctx=ast.Load()),args=[ast.Name(id='db',ctx=ast.Load()),params],keywords=[ast.keyword(arg=v,value=ast.Name(id=v,ctx=ast.Load())) for v in free])
   queries[domains[f.name]].append({'method':name,'scope':f.name,'statement':ast.unparse(expr),'free':free})
class Rewrite(ast.NodeTransformer):
 def visit_Call(self,n):
  if span(n) in sql:return self.generic_visit(copy.deepcopy(sql[span(n)]))
  return self.generic_visit(n)
 def visit_Name(self,n):
  if n.id=='self' and isinstance(n.ctx,ast.Load):return ast.Attribute(value=ast.Name(id='self',ctx=ast.Load()),attr='store',ctx=ast.Load())
  return n
outputs={};proof=[]
for domain in ('device_state','scheduling'):
 selected=[f for f in methods if domains[f.name]==domain]
 edits=[]
 for f in selected:
  for n in ast.walk(f):
   if isinstance(n,ast.Call) and span(n) in sql:edits.append((*span(n),ast.unparse(ast.fix_missing_locations(Rewrite().generic_visit(copy.deepcopy(sql[span(n)])))).encode()))
   elif isinstance(n,ast.Name) and n.id=='self' and isinstance(n.ctx,ast.Load):
    a,b=span(n)
    if not any(x<=a and b<=y for x,y in sql):edits.append((a,b,b'self.store'))
 changed=raw
 for a,b,text in sorted(edits,reverse=True):changed=changed[:a]+text+changed[b:]
 changed=changed.decode();parsed=ast.parse(changed);c=next(n for n in parsed.body if isinstance(n,ast.ClassDef));found={n.name:n for n in c.body if isinstance(n,ast.FunctionDef)}
 cls='DeviceStateService' if domain=='device_state' else 'SchedulingService';repo_cls='DeviceStateRepository' if domain=='device_state' else 'SchedulingRepository'
 imports='import json\n'
 if domain=='device_state':imports+='from ..policies import read_setting, set_disabled_workers\n'
 else:imports+='from ..core.clock import now\nfrom ..core.constants import ACTIVE, TERMINAL, V3_CODE_KEYS, V3_KEYS, V3_UPDATE_KEYS\nfrom ..errors import RuntimeRejected\nfrom ..policies import dispatch_held\n'
 imports+=f'from ..repositories.{domain} import {repo_cls} as repository\n'
 if domain in transaction:imports+='from ..db.transactions import begin_write\n'
 service='"""'+cls+' business operations behind the Store facade."""\n\n'+imports+'\n\nclass '+cls+':\n    def __init__(self, store):\n        self.store = store\n'
 for f in selected:
  service+='\n    '+ast.get_source_segment(changed,found[f.name])+'\n'
 actual_class=next(n for n in ast.parse(service).body if isinstance(n,ast.ClassDef));actual={n.name:n for n in actual_class.body if isinstance(n,ast.FunctionDef)}
 for f in selected:
  expected=Rewrite().visit(copy.deepcopy(f));assert ast.dump(expected,include_attributes=False)==ast.dump(actual[f.name],include_attributes=False),f.name
  proof.append({'method':f.name,'service':cls,'body':'same except self.store/repository/write-boundary forwarding','signature':'identical'})
 outputs[f'backend/services/{domain}.py']=service
 repo='"""'+repo_cls+' SQL."""\n\nfrom .base import execute\n\n\nclass '+repo_cls+':\n'
 for q in queries[domain]:
  extra=''.join(', '+n for n in q['free']);repo+='    @staticmethod\n    def '+q['method']+'(db, parameters=()'+(', *'+extra if extra else '')+'):\n        return execute(db, '+q['statement']+', parameters)\n\n'
 outputs[f'backend/repositories/{domain}.py']=repo
# Replace only the moved methods with same-signature delegators.
edits=[]
for f in methods:
 wrapper=copy.deepcopy(f);kws=[ast.keyword(arg=a.arg,value=ast.Name(id=a.arg,ctx=ast.Load())) for a in f.args.args+f.args.kwonlyargs if a.arg!='self']
 wrapper.body=[ast.Return(value=ast.Call(func=ast.Attribute(value=ast.Attribute(value=ast.Name(id='self',ctx=ast.Load()),attr=domains[f.name],ctx=ast.Load()),attr=f.name,ctx=ast.Load()),args=[],keywords=kws))]
 text=ast.unparse(ast.fix_missing_locations(wrapper)).replace('\n','\n    ');edits.append((*span(f),text.encode()))
for a,b,text in sorted(edits,reverse=True):raw=raw[:a]+text+raw[b:]
facade=raw.decode().replace('from .services.accounts import AccountService','from .services.accounts import AccountService\nfrom .services.device_state import DeviceStateService\nfrom .services.scheduling import SchedulingService')
facade=facade.replace('        self.accounts = AccountService(self)','        self.accounts = AccountService(self)\n        self.device_state = DeviceStateService(self)\n        self.scheduling = SchedulingService(self)')
outputs['backend/store.py']=facade
for file,text in outputs.items():ast.parse(text);(root/file).write_text(text)
(root/'.scratch/review-2026-11/B2/device-store-ast-proof.json').write_text(json.dumps({'base':'96d662e7','methods':proof,'queries':queries,'sqlCalls':len(sql),'comments':'preserved with source-span edits'},indent=2)+'\n')
print('Proved',len(proof),'Store methods,',len(sql),'SQL/write-boundary calls; preserved comments')
