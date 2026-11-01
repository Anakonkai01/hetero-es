"""Extract Store business bodies into domain services with exact normalized AST proof."""
import ast
import builtins
import copy
import json
from pathlib import Path
import re
import subprocess

root=Path('/home/pc5070ti/projects/heteroes')
source=subprocess.run(['git','show','07aba634:backend/store.py'],cwd=root,check=True,capture_output=True,text=True).stdout
tree=ast.parse(source);klass=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='Store')
clock=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='now')
domains={'cancel_selected':'experiments','cancel_owned':'experiments','eligibility':'experiments','get':'experiments','list':'experiments','save':'experiments','create':'experiments','snapshot':'experiments','workspaces':'workspaces'}
methods=[n for n in klass.body if isinstance(n,ast.FunctionDef) and n.name in domains]
raw=source.encode();starts=[0]
for line in raw.splitlines(keepends=True):starts.append(starts[-1]+len(line))
def span(n):return starts[n.lineno-1]+n.col_offset,starts[n.end_lineno-1]+n.end_col_offset
sql_map={};queries={'experiments':[],'workspaces':[]};names=set()
for f in methods:
 for n in ast.walk(f):
  if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and isinstance(n.func.value,ast.Name) and n.func.value.id=='db' and n.func.attr=='execute':
   expr=n.args[0]
   try:literal=ast.literal_eval(expr)
   except (ValueError,TypeError):literal=None
   text=literal if literal is not None else ''.join(x.value for x in ast.walk(expr) if isinstance(x,ast.Constant) and isinstance(x.value,str))
   verb=re.search(r'(?i)\b(SELECT|INSERT|UPDATE|DELETE|BEGIN)\b',text)[1].lower();table=re.search(r'(?i)\b(?:FROM|INTO|UPDATE)\s+([a-z_]+)',text)
   stem='state_'+f.name+'_'+verb+'_'+(table[1].lower() if table else 'value');name=stem;i=1
   while name in names:i+=1;name=stem+'_'+str(i)
   names.add(name)
   free=sorted({x.id for x in ast.walk(expr) if isinstance(x,ast.Name) and isinstance(x.ctx,ast.Load)}-set(dir(builtins)))
   params=copy.deepcopy(n.args[1]) if len(n.args)>1 else ast.Tuple(elts=[],ctx=ast.Load())
   call=ast.Call(func=ast.Attribute(value=ast.Name(id='repository',ctx=ast.Load()),attr=name,ctx=ast.Load()),args=[ast.Name(id='db',ctx=ast.Load()),params],keywords=[ast.keyword(arg=x,value=ast.Name(id=x,ctx=ast.Load())) for x in free])
   sql_map[span(n)]=call;queries[domains[f.name]].append({'method':name,'statement':ast.unparse(expr),'free':free,'scope':f.name})
class Rewrite(ast.NodeTransformer):
 def visit_Call(self,n):
  if span(n) in sql_map:return self.generic_visit(copy.deepcopy(sql_map[span(n)]))
  return self.generic_visit(n)
 def visit_Name(self,n):
  if n.id=='self' and isinstance(n.ctx,ast.Load):return ast.Attribute(value=ast.Name(id='self',ctx=ast.Load()),attr='store',ctx=ast.Load())
  return n
outputs={}
for domain in ('experiments','workspaces'):
 class_name='ExperimentStateService' if domain=='experiments' else 'WorkspaceStateService'
 if domain=='experiments':
  text='''"""Experiment state and admission business rules, behind the Store facade."""

import hashlib
import json
import uuid
from ..core.clock import now
from ..constants import TERMINAL, REVISION
from ..experiment_view import experiment_view
from ..repositories.experiments import ExperimentsRepository as repository
'''
 else:
  text=(root/'backend/services/workspaces.py').read_text().replace('from ..store import now','from ..core.clock import now')
 text+='\n\nclass '+class_name+':\n    def __init__(self, store):\n        self.store = store\n'
 for f in methods:
  if domains[f.name]!=domain:continue
  transformed=Rewrite().visit(copy.deepcopy(f));ast.fix_missing_locations(transformed)
  text+='\n'+'\n'.join('    '+line for line in ast.unparse(transformed).splitlines())+'\n'
 outputs['backend/services/'+('experiment_state' if domain=='experiments' else domain)+'.py']=text
 repo=(root/f'backend/repositories/{domain}.py').read_text()
 for q in queries[domain]:
  extra=''.join(', '+n for n in q['free'])
  repo+='\n    @staticmethod\n    def '+q['method']+'(db, parameters=()'+(', *'+extra if extra else '')+'):\n        return execute(db, '+q['statement']+', parameters)\n'
 outputs[f'backend/repositories/{domain}.py']=repo
# Keep the original facade signatures and route every operation to its owning service.
replacements=[]
for f in methods:
 wrapper=copy.deepcopy(f)
 target='experiments' if domains[f.name]=='experiments' else 'workspace_state'
 keywords=[ast.keyword(arg=a.arg,value=ast.Name(id=a.arg,ctx=ast.Load())) for a in f.args.args if a.arg!='self']
 keywords += [ast.keyword(arg=a.arg,value=ast.Name(id=a.arg,ctx=ast.Load())) for a in f.args.kwonlyargs]
 wrapper.body=[ast.Return(value=ast.Call(func=ast.Attribute(value=ast.Attribute(value=ast.Name(id='self',ctx=ast.Load()),attr=target,ctx=ast.Load()),attr=f.name,ctx=ast.Load()),args=[],keywords=keywords))]
 code=ast.unparse(ast.fix_missing_locations(wrapper));a,b=span(f);replacements.append((a,b,code.replace('\n','\n    ').encode()))
clock_a,clock_b=span(clock);replacements.append((clock_a,clock_b,b''))
for a,b,code in sorted(replacements,reverse=True):raw=raw[:a]+code+raw[b:]
facade=raw.decode().replace('from datetime import datetime, timezone\n','')
facade=facade.replace('from .services.accounts import AccountService','from .services.accounts import AccountService\nfrom .services.experiment_state import ExperimentStateService\nfrom .services.workspaces import WorkspaceStateService\nfrom .core.clock import now')
facade=facade.replace('        self.accounts = AccountService(self)','        self.accounts = AccountService(self)\n        self.experiments = ExperimentStateService(self)\n        self.workspace_state = WorkspaceStateService(self)')
outputs['backend/store.py']=facade
outputs['backend/core/clock.py']='"""Product UTC timestamp formatting shared by business services."""\n\nfrom datetime import datetime, timezone\n\n\n'+ast.get_source_segment(source,clock)+'\n'
# Check business bodies, facade signatures and the moved timestamp before writing any source.
proof=[]
for domain in ('experiments','workspaces'):
 file='backend/services/'+('experiment_state' if domain=='experiments' else domain)+'.py'
 t=ast.parse(outputs[file]);c=next(n for n in t.body if isinstance(n,ast.ClassDef) and n.name in ('ExperimentStateService','WorkspaceStateService'))
 actual={n.name:n for n in c.body if isinstance(n,ast.FunctionDef)}
 for f in methods:
  if domains[f.name]==domain:
   expected=Rewrite().visit(copy.deepcopy(f))
   assert ast.dump(expected,include_attributes=False)==ast.dump(actual[f.name],include_attributes=False),f.name
   proof.append({'method':f.name,'service':c.name,'bodyAST':'same after self.store forwarding and repository calls'})
facade_class=next(n for n in ast.parse(facade).body if isinstance(n,ast.ClassDef))
facade_methods={n.name:n for n in facade_class.body if isinstance(n,ast.FunctionDef)}
for f in methods:assert ast.dump(f.args)==ast.dump(facade_methods[f.name].args)
new_clock=next(n for n in ast.parse(outputs['backend/core/clock.py']).body if isinstance(n,ast.FunctionDef))
assert ast.dump(new_clock,include_attributes=False)==ast.dump(clock,include_attributes=False)
for file,text in outputs.items():ast.parse(text);(root/file).write_text(text)
(root/'.scratch/review-2026-11/B2/experiment-state-ast-proof.json').write_text(json.dumps({'base':'07aba634','methods':proof,'queries':queries,'clockAST':'identical','facadeSignatures':'identical'},indent=2)+'\n')
print('Extracted and proved',len(proof),'Store methods and',sum(map(len,queries.values())),'SQL calls; timestamp AST identical')
