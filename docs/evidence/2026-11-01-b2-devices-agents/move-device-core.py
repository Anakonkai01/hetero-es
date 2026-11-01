"""Move protocol constants/model bases/device contracts into core with normalized AST proof."""
import ast
import copy
import hashlib
import json
from pathlib import Path

root=Path('/home/pc5070ti/projects/heteroes')
constants=(root/'backend/constants.py').read_bytes();assert not (root/'backend/core/constants.py').exists()
policy=(root/'backend/policies.py').read_text();ptree=ast.parse(policy)
bases=[n for n in ptree.body if isinstance(n,ast.ClassDef) and n.name in ('Strict','FiniteStrict')];assert len(bases)==2
models='"""Shared validation model bases without HTTP or persistence dependencies."""\n\nfrom pydantic import BaseModel, ConfigDict\n\n\n'+'\n\n\n'.join(ast.get_source_segment(policy,n) for n in bases)+'\n'
plines=policy.splitlines(keepends=True)
for n in sorted(bases,key=lambda n:n.lineno,reverse=True):plines[n.lineno-1:n.end_lineno]=[]
new_policy=''.join(plines).replace('from pydantic import BaseModel, ConfigDict','from .core.models import Strict as Strict, FiniteStrict as FiniteStrict')
source=(root/'backend/device_models.py').read_text();tree=ast.parse(source);raw=source.encode();starts=[0]
for line in raw.splitlines(keepends=True):starts.append(starts[-1]+len(line))
def span(n):return starts[n.lineno-1]+n.col_offset,starts[n.end_lineno-1]+n.end_col_offset
changes=[]
def moved_import(n):
 n=copy.deepcopy(n)
 if n.module=='fastapi':return ast.ImportFrom(module='errors',names=[ast.alias(name='ServiceError')],level=1)
 if n.level:
  if n.module=='policies':n.module='models'
  elif n.module!='constants':n.level+=1
 return n
for n in ast.walk(tree):
 if isinstance(n,ast.ImportFrom):changes.append((*span(n),ast.unparse(moved_import(n)).encode()))
 elif isinstance(n,ast.Name) and n.id=='HTTPException':changes.append((*span(n),b'ServiceError'))
for a,b,text in sorted(changes,reverse=True):raw=raw[:a]+text+raw[b:]
contracts=raw.decode()
class Normalize(ast.NodeTransformer):
 def visit_ImportFrom(self,n):return moved_import(n)
 def visit_Name(self,n):
  if n.id=='HTTPException':return ast.Name(id='ServiceError',ctx=ast.Load())
  return n
assert ast.dump(Normalize().visit(copy.deepcopy(tree)),include_attributes=False)==ast.dump(ast.parse(contracts),include_attributes=False)
actual_bases=[n for n in ast.parse(models).body if isinstance(n,ast.ClassDef)]
assert [ast.dump(n,include_attributes=False) for n in bases]==[ast.dump(n,include_attributes=False) for n in actual_bases]
old_functions=[n for n in ptree.body if isinstance(n,ast.FunctionDef)];new_functions=[n for n in ast.parse(new_policy).body if isinstance(n,ast.FunctionDef)]
assert [ast.dump(n,include_attributes=False) for n in old_functions]==[ast.dump(n,include_attributes=False) for n in new_functions]
(root/'backend/core/constants.py').write_bytes(constants);(root/'backend/core/models.py').write_text(models);(root/'backend/core/device_models.py').write_text(contracts);(root/'backend/policies.py').write_text(new_policy)
for name in ('constants','device_models'):
 (root/f'backend/{name}.py').write_text('"""Compatibility module retained during core contract extraction."""\n\nimport sys\nfrom .core import '+name+' as _implementation\n\nsys.modules[__name__] = _implementation\n')
(root/'.scratch/review-2026-11/B2/device-core-ast-proof.json').write_text(json.dumps({'constantsBytesIdentical':True,'constantsSha256':hashlib.sha256(constants).hexdigest(),'modelBaseAST':'identical','policyFunctionAST':'identical','deviceContractAST':'identical except relocated imports and plain capability errors','compatibility':'module identity aliases for old imports'},indent=2)+'\n')
print('Core constants byte-identical, model bases/policy bodies unchanged; device contract AST normalized and checked')
