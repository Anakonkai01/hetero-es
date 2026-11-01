"""Separate filesystem storage/capabilities from HTTP streaming without changing upload ownership."""
import ast
import copy
import json
from pathlib import Path
import subprocess
import sys

root=Path('/home/pc5070ti/projects/heteroes');output=Path(sys.argv[1]) if len(sys.argv)>1 else root
source=subprocess.run(['git','show','401cb4e1:backend/local_storage.py'],cwd=root,check=True,capture_output=True,text=True).stdout
raw=source.encode();tree=ast.parse(source);classes={n.name:n for n in tree.body if isinstance(n,ast.ClassDef)}
klass=classes['LocalBackend'];install=next(n for n in klass.body if isinstance(n,ast.FunctionDef) and n.name=='install_routes')
starts=[0]
for line in raw.splitlines(keepends=True):starts.append(starts[-1]+len(line))
def span(n):return starts[n.lineno-1]+n.col_offset,starts[n.end_lineno-1]+n.end_col_offset
edits=[]
for node in ast.walk(tree):
 if isinstance(node,ast.ImportFrom):
  if node.module=='fastapi':edits.append((*span(node),b'from ..core.errors import ServiceError'))
  elif node.module in ('fastapi.responses','starlette.concurrency','anyio'):edits.append((*span(node),b''))
  elif node.level:
   assert node.module=='devices' and node.level==1
   edits.append((*span(node),b'from ..core.device_models import Enrollment'))
 elif isinstance(node,ast.Name) and node.id=='HTTPException' and not (install.lineno<=node.lineno<=install.end_lineno):edits.append((*span(node),b'ServiceError'))
replacement='def install_routes(self, app):\n    from ..api.local_storage import install_routes\n\n    return install_routes(app, self)'
edits.append((*span(install),replacement.replace('\n','\n    ').encode()))
for a,b,text in sorted(edits,reverse=True):raw=raw[:a]+text+raw[b:]
implementation=raw.decode();actual_classes={n.name:n for n in ast.parse(implementation).body if isinstance(n,ast.ClassDef)}
class BusinessRewrite(ast.NodeTransformer):
 def visit_Name(self,node):
  return ast.Name(id='ServiceError',ctx=node.ctx) if node.id=='HTTPException' else node
 def visit_ImportFrom(self,node):
  if node.level:
   node=copy.deepcopy(node);node.level=2;node.module='core.device_models'
  return node
for name,old in classes.items():
 new=copy.deepcopy(actual_classes[name]);expected=BusinessRewrite().visit(copy.deepcopy(old))
 if name=='LocalBackend':
  new.body=[n for n in new.body if not isinstance(n,ast.FunctionDef) or n.name!='install_routes']
  expected.body=[n for n in expected.body if not isinstance(n,ast.FunctionDef) or n.name!='install_routes']
 assert ast.dump(expected,include_attributes=False)==ast.dump(new,include_attributes=False),name
class HttpRewrite(ast.NodeTransformer):
 def visit_Name(self,node):
  if node.id=='self':return ast.Name(id='backend',ctx=node.ctx)
  if node.id in ('_Upload','PUBLIC_STUDY_MAX_BYTES'):return ast.Attribute(value=ast.Name(id='local',ctx=ast.Load()),attr=node.id,ctx=node.ctx)
  return node
api_install=HttpRewrite().visit(copy.deepcopy(install));api_install.args.args=[ast.arg(arg='app'),ast.arg(arg='backend')]
handler=ast.parse('try:\n    pass\nexcept ServiceError as error:\n    raise HTTPException(error.status_code, error.detail, headers=error.headers) from None\n').body[0].handlers[0]
for function in api_install.body:
 if not isinstance(function,(ast.FunctionDef,ast.AsyncFunctionDef)):continue
 if function.name in ('public_study','download'):
  function.body=[ast.Try(body=function.body,handlers=[copy.deepcopy(handler)],orelse=[],finalbody=[])]
 elif function.name=='receive':
  assert len(function.body)==2 and isinstance(function.body[1],ast.Try)
  function.body[1]=ast.Try(body=[function.body[1]],handlers=[copy.deepcopy(handler)],orelse=[],finalbody=[])
old_endpoints={n.name:n for n in install.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and n.decorator_list}
for n in api_install.body:
 if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and n.decorator_list:
  assert ast.dump(n.args)==ast.dump(old_endpoints[n.name].args)
  assert [ast.dump(d) for d in n.decorator_list]==[ast.dump(d) for d in old_endpoints[n.name].decorator_list]
api='"""Signed filesystem HTTP transfers; blocking disk work stays off the event loop."""\n\nfrom anyio import CancelScope\nfrom fastapi import HTTPException, Request\nfrom fastapi.responses import FileResponse\nfrom starlette.concurrency import run_in_threadpool\nfrom ..core.errors import ServiceError\nfrom ..storage import local_backend as local\n\n'+ast.unparse(ast.fix_missing_locations(api_install))+'\n'
for file,text in [('backend/storage/__init__.py','"""Object storage implementations."""\n'),('backend/storage/local_backend.py',implementation),('backend/api/local_storage.py',api),('backend/local_storage.py','"""Public compatibility namespace for filesystem storage and instrumentation."""\n\nimport sys\nfrom .storage import local_backend as _implementation\n\nsys.modules[__name__] = _implementation\n')]:
 ast.parse(text);p=output/file;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(text)
(root/'.scratch/review-2026-11/B2/local-backend-ast-proof.json').write_text(json.dumps({'base':'401cb4e1','businessClassAST':'identical except plain errors and core Enrollment import; HTTP installer delegates','httpSignaturesAndDecorators':'identical','httpBody':'self renamed backend; public instrumentation references module; API converts ServiceError to HTTPException for standalone apps','asyncOwnership':'same off-loop calls, stream iteration and shielded close finally; error mapping wraps the original block','namespace':'backend.local_storage and storage.local_backend share module identity'},indent=2)+'\n')
print('Proved filesystem class bodies and HTTP signatures; preserved async upload ownership')
