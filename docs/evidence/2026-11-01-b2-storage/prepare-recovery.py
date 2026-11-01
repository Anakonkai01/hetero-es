"""Split recovery request/cookie operations from business state before the generic layer extraction."""
import ast
import copy
import json
from pathlib import Path
import subprocess
import sys
import textwrap

root=Path('/home/pc5070ti/projects/heteroes')
output=Path(sys.argv[1]) if len(sys.argv)>1 else root
scratch=root/'.scratch/review-2026-11/B2'
source=subprocess.run(['git','show','401cb4e1:backend/recovery_storage.py'],cwd=root,check=True,capture_output=True,text=True).stdout
raw=source.encode();tree=ast.parse(source);factory=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='install_storage_routes')
starts=[0]
for line in raw.splitlines(keepends=True):starts.append(starts[-1]+len(line))
def span(n):return starts[n.lineno-1]+n.col_offset,starts[n.end_lineno-1]+n.end_col_offset
def statements(text):return ast.parse(text).body
functions={n.name:n for n in factory.body if isinstance(n,ast.FunctionDef)}
ticket=functions['ticket'];consume=functions['consume']
prepared_ticket=copy.deepcopy(ticket);prepared_ticket.decorator_list=[]
prepared_ticket.args.args=[copy.deepcopy(ticket.args.args[0]),ast.arg(arg='token',annotation=ast.Name(id='str',ctx=ast.Load())),copy.deepcopy(ticket.args.args[-1])]
assert [n.arg for n in ticket.args.args]==['artifact_id','response','request','current']
body=[];cookie=None
for statement in prepared_ticket.body:
 if isinstance(statement,ast.Assign) and any(isinstance(n,ast.Name) and n.id=='session_digest' for n in statement.targets):
  old=statement.value.func.value.args[0].func.value
  assert ast.unparse(old)=='request.headers.get(\'Authorization\', \'\')[7:]'
  statement.value.func.value.args[0].func.value=ast.Name(id='token',ctx=ast.Load())
 if isinstance(statement,ast.Expr) and isinstance(statement.value,ast.Call) and isinstance(statement.value.func,ast.Attribute) and statement.value.func.attr=='set_cookie':
  cookie=copy.deepcopy(statement);continue
 if isinstance(statement,ast.Return):
  assert ast.unparse(statement.value)=="{'downloadUrl': path}"
  statement.value.keys.append(ast.Constant(value='secret'));statement.value.values.append(ast.Name(id='secret',ctx=ast.Load()))
 body.append(statement)
assert cookie is not None
prepared_ticket.body=body
prepared_consume=copy.deepcopy(consume);prepared_consume.decorator_list=[]
assert [n.arg for n in consume.args.args]==['ticket_digest','request']
prepared_consume.args.args[-1]=ast.arg(arg='secret',annotation=ast.Name(id='str',ctx=ast.Load()))
assert isinstance(prepared_consume.body[0],ast.Assign) and ast.unparse(prepared_consume.body[0].value)=="request.cookies.get('heteroes-cloud-download', '')"
prepared_consume.body=prepared_consume.body[1:]
response_index=next(i for i,n in enumerate(prepared_consume.body) if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='response' for t in n.targets))
response_statement=prepared_consume.body[response_index]
assert isinstance(response_statement.value,ast.Call) and response_statement.value.func.id=='RedirectResponse'
url=copy.deepcopy(response_statement.value.args[0]);prepared_consume.body=prepared_consume.body[:response_index]+[ast.Return(value=url)]
# HTTP signatures/decorators and cookie/redirect operations are preserved from the old endpoint.
api_ticket=copy.deepcopy(ticket)
api_ticket.body=statements("result = service.ticket(artifact_id=artifact_id, token=request.headers.get('Authorization', '')[7:], current=current)\npath = result['downloadUrl']\n")
class CookieSecret(ast.NodeTransformer):
 def visit_Name(self,node):
  return ast.Subscript(value=ast.Name(id='result',ctx=ast.Load()),slice=ast.Constant(value='secret'),ctx=ast.Load()) if node.id=='secret' else node
api_ticket.body += [CookieSecret().visit(cookie),ast.Return(value=ast.Dict(keys=[ast.Constant(value='downloadUrl')],values=[ast.Name(id='path',ctx=ast.Load())]))]
api_consume=copy.deepcopy(consume)
api_consume.body=statements("url = service.consume(ticket_digest=ticket_digest, secret=request.cookies.get('heteroes-cloud-download', ''))\n")
response_statement=copy.deepcopy(consume.body[response_index+1]);response_statement.value.args[0]=ast.Name(id='url',ctx=ast.Load())
api_consume.body += [response_statement]+copy.deepcopy(consume.body[response_index+2:])
assert ast.dump(api_ticket.args)==ast.dump(ticket.args) and ast.dump(api_consume.args)==ast.dump(consume.args)
classes=[n for n in factory.body if isinstance(n,ast.ClassDef)];assert [n.name for n in classes]==['Begin','Finish']
core='"""Recovery request contracts shared by HTTP adapters and services."""\n\nfrom pydantic import BaseModel, ConfigDict, Field\n\n'
for node in classes:core+=textwrap.dedent('    '+ast.get_source_segment(source,node))+'\n\n'
for a,b in zip(classes,[n for n in ast.parse(core).body if isinstance(n,ast.ClassDef)]):assert ast.dump(a,include_attributes=False)==ast.dump(b,include_attributes=False)
imports=[n for n in factory.body if isinstance(n,(ast.Import,ast.ImportFrom))]
edits=[(*span(n),b'') for n in classes+imports]
for old,new in [(ticket,prepared_ticket),(consume,prepared_consume)]:
 text=ast.unparse(ast.fix_missing_locations(new)).replace('\n','\n    ');edits.append((*span(old),text.encode()))
for a,b,text in sorted(edits,reverse=True):raw=raw[:a]+text+raw[b:]
prepared='from .core.storage_models import Begin, Finish\n'+'\n'.join(ast.unparse(n) for n in imports)+'\n'+raw.decode()
ast.parse(prepared)
(output/'backend/core').mkdir(parents=True,exist_ok=True)
(output/'backend/core/storage_models.py').write_text(core)
(scratch/'recovery_storage-prepared.py').write_text(prepared)
(scratch/'recovery-http-overrides.py').write_text('\n\n'.join(ast.unparse(ast.fix_missing_locations(n)) for n in [api_ticket,api_consume])+'\n')
(scratch/'recovery-boundary-proof.json').write_text(json.dumps({'base':'401cb4e1','coreRequestClasses':'same AST','httpSignaturesAndDecorators':'same AST','cookieAndRedirectOperations':'same AST except secret/result and service URL references','serviceTicket':'same body except token input replaces Request header, cookie output moves to API; returns internal secret alongside path','serviceConsume':'same body except cookie input replaces Request and URL replaces HTTP response','originalHttpArgs':{n.name:ast.dump(n.args,include_attributes=False) for n in [ticket,consume]},'originalDecorators':{n.name:[ast.dump(d,include_attributes=False) for d in n.decorator_list] for n in [ticket,consume]}},indent=2)+'\n')
print('Prepared recovery cookie/header boundary and two unchanged request contracts')
