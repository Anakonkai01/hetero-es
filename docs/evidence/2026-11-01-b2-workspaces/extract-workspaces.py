"""Extract existing workspace operations; prove only the enumerated AST rewrites occurred."""
import ast
import copy
import io
import json
from pathlib import Path
import re
import tokenize
import subprocess

root=Path('/home/pc5070ti/projects/heteroes')
path=root/'backend/routes_workspaces.py'
source=subprocess.run(['git','show','74deec97:backend/routes_workspaces.py'],cwd=root,check=True,capture_output=True,text=True).stdout
tree=ast.parse(source)
install=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='install_routes')
functions=[n for n in install.body if isinstance(n,ast.FunctionDef)]
endpoints=[n for n in functions if n.decorator_list]
raw=source.encode();lines=raw.splitlines(keepends=True);starts=[0]
for line in lines:starts.append(starts[-1]+len(line))
def span(n):return starts[n.lineno-1]+n.col_offset,starts[n.end_lineno-1]+n.end_col_offset
replacements=[];queries=[];by_line={};names=set()
for f in functions:
    for node in ast.walk(f):
        if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute) and isinstance(node.func.value,ast.Name) and node.func.value.id=='db' and node.func.attr=='execute':
            sql=ast.literal_eval(node.args[0]);assert isinstance(sql,str)
            verb=sql.split()[0].lower()
            table=re.search(r'(?i)\b(?:FROM|INTO|UPDATE)\s+([a-z_]+)',sql)
            stem=f.name+'_'+verb+'_'+(table[1].lower() if table else 'value')
            name=stem;i=1
            while name in names:i+=1;name=stem+'_'+str(i)
            names.add(name)
            args=[copy.deepcopy(node.func.value),*copy.deepcopy(node.args[1:])]
            call=ast.Call(func=ast.Attribute(value=ast.Name(id='repository',ctx=ast.Load()),attr=name,ctx=ast.Load()),args=args,keywords=copy.deepcopy(node.keywords))
            by_line[(node.lineno,node.col_offset)]=call
            replacements.append((*span(node),ast.unparse(call).encode()))
            queries.append({'name':name,'scope':f.name,'sql':sql,'line':node.lineno})
        elif isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and node.func.id=='Response':
            assert f in endpoints
            assert len(node.keywords)==1 and node.keywords[0].arg=='status_code' and node.keywords[0].value.value==204
            assert any(any(k.arg=='status_code' and isinstance(k.value,ast.Constant) and k.value.value==204 for k in d.keywords) for d in f.decorator_list)
            replacements.append((*span(node),b'None'))
        elif isinstance(node,ast.Attribute) and isinstance(node.value,ast.Name) and node.value.id=='sqlite3' and node.attr=='IntegrityError':
            replacements.append((*span(node),b'DatabaseConflict'))
        elif isinstance(node,ast.Name) and node.id=='HTTPException':
            replacements.append((*span(node),b'ServiceError'))
assert len(queries)==30
for a,b,value in sorted(replacements,reverse=True):raw=raw[:a]+value+raw[b:]
changed=raw.decode();changed_tree=ast.parse(changed)
changed_install=next(n for n in changed_tree.body if isinstance(n,ast.FunctionDef) and n.name=='install_routes')
changed_functions=[n for n in changed_install.body if isinstance(n,ast.FunctionDef)]

def signature(f):
    result=copy.deepcopy(f)
    positional=result.args.posonlyargs+result.args.args
    defaults={a.arg:d for a,d in zip(positional[-len(result.args.defaults):],result.args.defaults)} if result.args.defaults else {}
    dependent=[a for a in positional if isinstance(defaults.get(a.arg),ast.Call) and isinstance(defaults[a.arg].func,ast.Name) and defaults[a.arg].func.id=='Depends']
    result.args.posonlyargs=[a for a in result.args.posonlyargs if a not in dependent]
    result.args.args=[a for a in result.args.args if a not in dependent]
    result.args.defaults=[defaults[a.arg] for a in result.args.posonlyargs+result.args.args if a.arg in defaults]
    result.args.kwonlyargs+=dependent;result.args.kw_defaults += [None]*len(dependent)
    result.decorator_list=[]
    return result

service='''"""Workspace membership, admission and queue visibility business operations."""

import json
import uuid
from types import SimpleNamespace
from ..request_models import DefaultCoordinator, WorkspaceCreate, Invite, JoinDecision, Listing, MemberEdit
from ..policies import dispatch_held, set_disabled_workers
from ..store import now
from ..core.errors import ServiceError, DatabaseConflict
from ..repositories.workspaces import WorkspacesRepository as repository


def operations(store, scoped, active, workspace_admin):
'''
changed_lines=changed.splitlines(keepends=True)
for f in changed_functions:
    seg=ast.get_source_segment(changed,f)
    depth=0;header_end=None
    for token in tokenize.generate_tokens(io.StringIO(seg).readline):
        if token.type==tokenize.OP:
            if token.string in ('(', '[', '{'):depth+=1
            elif token.string in (')',']','}'):depth-=1
            elif token.string==':' and depth==0:header_end=token.end[0];break
    assert header_end
    sig=signature(f);sig.body=[ast.Pass()]
    header=ast.unparse(ast.fix_missing_locations(sig)).split('\n',1)[0]
    body=''.join(changed_lines[f.lineno-1+header_end:f.end_lineno])
    service+='    '+header+'\n'+body+'\n'
service+='    return SimpleNamespace('+', '.join(f'{f.name}={f.name}' for f in endpoints)+')\n'

api='''"""Workspace HTTP adapters; operations and persistence are separate."""

from fastapi import APIRouter, Depends, Response
from ..request_models import DefaultCoordinator, WorkspaceCreate, Invite, JoinDecision, Listing, MemberEdit
from ..services.workspaces import operations


def install_routes(app, store, scoped, active, workspace_admin):
    service = operations(store, scoped, active, workspace_admin)
    router = APIRouter()
'''
for f in endpoints:
    wrapper=copy.deepcopy(f)
    arguments=[ast.keyword(arg=a.arg,value=ast.Name(id=a.arg,ctx=ast.Load())) for a in f.args.posonlyargs+f.args.args+f.args.kwonlyargs]
    call=ast.Call(func=ast.Attribute(value=ast.Name(id='service',ctx=ast.Load()),attr=f.name,ctx=ast.Load()),args=[],keywords=arguments)
    no_body=any(any(k.arg=='status_code' and isinstance(k.value,ast.Constant) and k.value.value==204 for k in d.keywords) for d in f.decorator_list)
    wrapper.body=([ast.Expr(value=call),ast.Return(value=ast.Call(func=ast.Name(id='Response',ctx=ast.Load()),args=[],keywords=[ast.keyword(arg='status_code',value=ast.Constant(value=204))]))] if no_body else [ast.Return(value=call)])
    api+='\n'+'\n'.join('    '+line for line in ast.unparse(ast.fix_missing_locations(wrapper)).splitlines())+'\n'
api+='\n    app.include_router(router)\n'
repo='''"""Workspace SQL; transaction boundaries belong to business operations."""

from .base import execute


class WorkspacesRepository:
'''
for q in queries:
    repo+='    @staticmethod\n    def '+q['name']+'(db, parameters=()):\n        return execute(db, '+repr(q['sql'])+', parameters)\n\n'

class Expected(ast.NodeTransformer):
    def visit_Name(self,node):
        if node.id=='HTTPException':return ast.Name(id='ServiceError',ctx=ast.Load())
        return node
    def visit_Call(self,node):
        if (node.lineno,node.col_offset) in by_line and isinstance(node.func,ast.Attribute) and isinstance(node.func.value,ast.Name) and node.func.value.id=='db' and node.func.attr=='execute':return copy.deepcopy(by_line[(node.lineno,node.col_offset)])
        if isinstance(node.func,ast.Name) and node.func.id=='Response':return ast.Constant(value=None)
        return self.generic_visit(node)
    def visit_Attribute(self,node):
        if isinstance(node.value,ast.Name) and node.value.id=='sqlite3' and node.attr=='IntegrityError':return ast.Name(id='DatabaseConflict',ctx=ast.Load())
        return self.generic_visit(node)
service_tree=ast.parse(service);actual_factory=next(n for n in service_tree.body if isinstance(n,ast.FunctionDef) and n.name=='operations')
actual={n.name:n for n in actual_factory.body if isinstance(n,ast.FunctionDef)}
for original in functions:
    expected=signature(Expected().visit(copy.deepcopy(original)))
    assert ast.dump(expected,include_attributes=False)==ast.dump(actual[original.name],include_attributes=False),original.name
api_tree=ast.parse(api);api_factory=next(n for n in api_tree.body if isinstance(n,ast.FunctionDef))
wrappers={n.name:n for n in api_factory.body if isinstance(n,ast.FunctionDef)}
for original in endpoints:
    wrapper=wrappers[original.name]
    assert ast.dump(wrapper.args)==ast.dump(original.args)
    assert [ast.dump(n) for n in wrapper.decorator_list]==[ast.dump(n) for n in original.decorator_list]
for filename,text in [('backend/api/workspaces.py',api),('backend/services/workspaces.py',service),('backend/repositories/workspaces.py',repo)]:
    (root/filename).write_text(text)
path.write_text('"""Compatibility import retained during the three-layer extraction."""\n\nfrom .api.workspaces import install_routes as install_routes\n')
(root/'.scratch/review-2026-11/B2/workspaces-ast-proof.json').write_text(json.dumps({'sqlCalls':len(queries),'businessFunctions':len(functions),'httpFunctions':len(endpoints),'businessAST':'identical except repository calls, plain service/conflict errors, dependency parameters and HTTP response removal','httpSignaturesAndDecorators':'identical','queries':queries},indent=2)+'\n')
print('Proved and extracted',len(queries),'queries,',len(functions),'business functions,',len(endpoints),'HTTP adapters')
