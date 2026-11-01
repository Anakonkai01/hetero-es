"""Move route business bodies and SQL with an explicit, independently checked AST rewrite set."""
import ast
import builtins
import copy
import io
import json
from pathlib import Path
import re
import subprocess
import sys
import tokenize

root=Path('/home/pc5070ti/projects/heteroes')
domain=sys.argv[1]
assert domain in ('experiments','history','templates','notifications','devices')
keep={'experiments':{'run_stream'},'history':{'download'},'templates':set(),'notifications':set(),'devices':set()}[domain]
expected_count={'experiments':8,'history':3,'templates':5,'notifications':16,'devices':52}[domain]
install_name={'templates':'install_template_routes','notifications':'install_notification_routes','devices':'install_device_routes'}.get(domain,'install_routes')
source_file=f'backend/{domain}.py' if domain in ('templates','notifications','devices') else f'backend/routes_{domain}.py'
repo_class=domain.title()+'Repository'
source=subprocess.run(['git','show',f'499e59ac:{source_file}'],cwd=root,check=True,capture_output=True,text=True).stdout
if domain=='devices':source=(root/'.scratch/review-2026-11/B2/device-source-prepared.py').read_text()
projection_text=None
if domain=='notifications':
    original_tree=ast.parse(source)
    notification_class=next(n for n in original_tree.body if isinstance(n,ast.ClassDef) and n.name=='Notifications')
    constructor=next(n for n in notification_class.body if isinstance(n,ast.FunctionDef) and n.name=='__init__')
    block=next(n for n in constructor.body if isinstance(n,ast.With))
    assert len(block.body)==2
    assert isinstance(block.body[0],ast.Expr) and isinstance(block.body[0].value,ast.Call) and block.body[0].value.func.id=='initialize_notifications_schema'
    assert ast.literal_eval(block.body[1].value.args[0]).startswith('CREATE INDEX IF NOT EXISTS notifications_user')
    projection_text='\"\"\"Notification projection schema initialization, owned by the database layer.\"\"\"\n\nfrom .migrations import initialize_notifications_schema\n\n\ndef initialize_notification_projection(db):\n'
    projection_text+='\n'.join('    '+line for n in block.body for line in ast.unparse(n).splitlines())+'\n'
    actual=next(n for n in ast.parse(projection_text).body if isinstance(n,ast.FunctionDef))
    assert [ast.dump(n,include_attributes=False) for n in actual.body]==[ast.dump(n,include_attributes=False) for n in block.body]
    lines=source.splitlines(keepends=True);lines[block.body[0].lineno-1:block.body[-1].end_lineno]=['            initialize_notification_projection(db)\n'];source=''.join(lines)
    (root/'.scratch/review-2026-11/B2/notifications-schema-proof.json').write_text(json.dumps({'initializerStatementsAST':'identical','relocatedIndex':True,'source':'Notifications.__init__ at499e59ac','destination':'backend/db/projections.py'},indent=2)+'\n')
tree=ast.parse(source);install=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name==install_name)
functions=[n for n in install.body if isinstance(n,ast.FunctionDef)]
endpoints=[n for n in functions if n.decorator_list]
business=[n for n in functions if n.name not in keep]
global_business=[n for n in tree.body if isinstance(n,(ast.FunctionDef,ast.ClassDef)) and n is not install]
endpoint_map={n.name:n for n in endpoints}
dependency_names={n.args[0].id for f in functions for n in ast.walk(f.args) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='Depends' and n.args and isinstance(n.args[0],ast.Name)}
dependencies=[f for f in functions if not f.decorator_list and f.name in dependency_names]
raw=source.encode();starts=[0]
for line in raw.splitlines(keepends=True):starts.append(starts[-1]+len(line))
def span(n):return starts[n.lineno-1]+n.col_offset,starts[n.end_lineno-1]+n.end_col_offset

def dependent_positions(f):
    args=f.args.posonlyargs+f.args.args
    defaults={a.arg:d for a,d in zip(args[-len(f.args.defaults):],f.args.defaults)} if f.args.defaults else {}
    return {i:a.arg for i,a in enumerate(args) if isinstance(defaults.get(a.arg),ast.Call) and isinstance(defaults[a.arg].func,ast.Name) and defaults[a.arg].func.id in ('Depends','Header')}

def signature(f):
    result=copy.deepcopy(f);positions=dependent_positions(result)
    args=result.args.posonlyargs+result.args.args;dependent=[a for i,a in enumerate(args) if i in positions]
    defaults={a.arg:d for a,d in zip(args[-len(result.args.defaults):],result.args.defaults)} if result.args.defaults else {}
    result.args.posonlyargs=[a for a in result.args.posonlyargs if a not in dependent]
    result.args.args=[a for a in result.args.args if a not in dependent]
    result.args.defaults=[defaults[a.arg] for a in result.args.posonlyargs+result.args.args if a.arg in defaults]
    result.args.kwonlyargs+=dependent;result.args.kw_defaults += [None]*len(dependent);result.decorator_list=[]
    return result

rewrites={};queries=[];query_count=0;names=set();uses_transaction=False
for f in business+global_business:
    for node in ast.walk(f):
        if not hasattr(node,'lineno'):continue
        key=span(node)
        if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute) and isinstance(node.func.value,ast.Name) and node.func.value.id=='db' and node.func.attr=='execute':
            query_count+=1;sql=node.args[0]
            try:literal=ast.literal_eval(sql)
            except (ValueError,TypeError):literal=None
            if literal=='BEGIN IMMEDIATE':
                call=ast.Call(func=ast.Name(id='begin_write',ctx=ast.Load()),args=[copy.deepcopy(node.func.value)],keywords=[]);uses_transaction=True
            else:
                text=literal if literal is not None else ast.unparse(sql)
                verb=re.search(r'(?i)\b(SELECT|INSERT|UPDATE|DELETE|BEGIN)\b',text)[1].lower() if text else 'query';table=re.search(r'(?i)\b(?:FROM|INTO|UPDATE)\s+([a-z_]+)',text)
                scope=f
                if isinstance(f,ast.ClassDef):
                    scopes=[n for n in ast.walk(f) if isinstance(n,ast.FunctionDef) and n.lineno<=node.lineno<=n.end_lineno]
                    if scopes:scope=min(scopes,key=lambda n:n.end_lineno-n.lineno)
                stem=scope.name+'_'+verb+'_'+(table[1].lower() if table else 'value');name=stem;i=1
                while name in names:i+=1;name=stem+'_'+str(i)
                names.add(name)
                free=sorted({n.id for n in ast.walk(sql) if isinstance(n,ast.Name) and isinstance(n.ctx,ast.Load)}-set(dir(builtins)))
                parameters=copy.deepcopy(node.args[1]) if len(node.args)>1 else ast.Tuple(elts=[],ctx=ast.Load())
                call=ast.Call(func=ast.Attribute(value=ast.Name(id='repository',ctx=ast.Load()),attr=name,ctx=ast.Load()),args=[copy.deepcopy(node.func.value),parameters],keywords=[ast.keyword(arg=n,value=ast.Name(id=n,ctx=ast.Load())) for n in free])
                queries.append({'name':name,'scope':scope.name,'statement':ast.unparse(sql),'dynamic':literal is None,'free':free,'line':node.lineno})
            rewrites[key]=call
        elif isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and node.func.id=='Response':
            assert len(node.keywords)==1 and node.keywords[0].arg=='status_code' and node.keywords[0].value.value==204
            assert any(any(k.arg=='status_code' and isinstance(k.value,ast.Constant) and k.value.value==204 for k in d.keywords) for d in f.decorator_list)
            rewrites[key]=ast.Constant(value=None)
        elif isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and node.func.id in endpoint_map:
            dependencies=dependent_positions(endpoint_map[node.func.id]);provided={i:n for i,n in dependencies.items() if i<len(node.args)}
            if provided:
                call=copy.deepcopy(node);call.args=[a for i,a in enumerate(node.args) if i not in provided];call.keywords += [ast.keyword(arg=n,value=copy.deepcopy(node.args[i])) for i,n in provided.items()];rewrites[key]=call
        elif isinstance(node,ast.Name) and node.id=='HTTPException':rewrites[key]=ast.Name(id='ServiceError',ctx=ast.Load())
assert query_count==expected_count,(domain,query_count)
for a,b in rewrites:
    assert not any(c<a<d<b or a<c<b<d or (a<c and d<b) for c,d in rewrites if (a,b)!=(c,d)), 'overlapping source changes'
for (a,b),node in sorted(rewrites.items(),reverse=True):raw=raw[:a]+ast.unparse(ast.fix_missing_locations(node)).encode()+raw[b:]
changed=raw.decode();parsed=ast.parse(changed);factory=next(n for n in parsed.body if isinstance(n,ast.FunctionDef) and n.name==install_name)
changed_funcs={n.name:n for n in factory.body if isinstance(n,ast.FunctionDef)}
imports=[copy.deepcopy(n) for n in tree.body if isinstance(n,(ast.Import,ast.ImportFrom))]
for n in imports:
    if isinstance(n,ast.ImportFrom) and n.level:
        n.level+=1
        if n.module=='migrations':n.module='db.migrations'
        elif n.module=='device_models':n.module='core.device_models'
        elif n.module=='constants':n.module='core.constants'
service_imports=[n for n in imports if not (isinstance(n,ast.ImportFrom) and (n.module or '').startswith(('fastapi','starlette')))]
api_imports=imports
if domain=='devices':api_imports=[*api_imports,ast.ImportFrom(module='fastapi',names=[ast.alias(name='Response')],level=0)]
if not any(isinstance(n,ast.ImportFrom) and n.module=='fastapi' and any(a.name=='APIRouter' for a in n.names) for n in imports):
    api_imports=[*api_imports,ast.ImportFrom(module='fastapi',names=[ast.alias(name='APIRouter')],level=0)]
service='"""'+domain.title()+' business operations; HTTP responses stay in api/."""\n\n'
service+='\n'.join(ast.unparse(n) for n in service_imports)+'\nfrom types import SimpleNamespace\nfrom ..core.errors import ServiceError\n'
service+=f'from ..repositories.{domain} import {repo_class} as repository\n'
if uses_transaction:service+='from ..db.transactions import begin_write\n'
if domain=='notifications':service+='from ..db.projections import initialize_notification_projection\n'
for n in parsed.body:
    if not isinstance(n,(ast.Import,ast.ImportFrom)) and n is not factory and not (isinstance(n,ast.Expr) and isinstance(n.value,ast.Constant) and isinstance(n.value.value,str)):
        service+='\n'+ast.get_source_segment(changed,n)+'\n'
outer=[a.arg for a in install.args.args if a.arg!='app']
service+='\n\ndef operations('+', '.join(outer)+'):\n'
prelude=[n for n in factory.body if not isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef,ast.Return)) and not (isinstance(n,ast.Assign) and isinstance(n.value,ast.Call) and isinstance(n.value.func,ast.Name) and n.value.func.id=='APIRouter') and not (isinstance(n,ast.Expr) and isinstance(n.value,ast.Call) and isinstance(n.value.func,ast.Attribute) and n.value.func.attr=='include_router')]
for n in prelude:service+='\n'.join('    '+line for line in ast.unparse(n).splitlines())+'\n'
changed_lines=changed.splitlines(keepends=True)
for old in business:
    f=changed_funcs[old.name];seg=ast.get_source_segment(changed,f);depth=0;header_end=None
    for token in tokenize.generate_tokens(io.StringIO(seg).readline):
        if token.type==tokenize.OP:
            if token.string in ('(', '[', '{'):depth+=1
            elif token.string in (')',']','}'):depth-=1
            elif token.string==':' and depth==0:header_end=token.end[0];break
    assert header_end
    sig=signature(f);sig.body=[ast.Pass()]
    service+='    '+ast.unparse(ast.fix_missing_locations(sig)).split('\n',1)[0]+'\n'+''.join(changed_lines[f.lineno-1+header_end:f.end_lineno])+'\n'
service+='    return SimpleNamespace('+', '.join(f'{f.name}={f.name}' for f in business)+')\n'
api='"""'+domain.title()+' HTTP adapters."""\n\n'+'\n'.join(ast.unparse(n) for n in api_imports)+f'\nfrom ..services.{domain} import operations\n\n\ndef install_routes('+', '.join(a.arg for a in install.args.args)+'):\n'
api+='    service = operations('+', '.join(outer)+')\n    router = APIRouter()\n'
helper_names={f.name for f in business};aliases=set()
for f in endpoints:
    if f.name in keep:
        aliases|={n.id for n in ast.walk(f) if isinstance(n,ast.Name) and isinstance(n.ctx,ast.Load) and n.id in helper_names}
for name in sorted(aliases):api+=f'    {name} = service.{name}\n'
if domain=='devices':api+='\n'+(root/'.scratch/review-2026-11/B2/device-api-auth.txt').read_text()
for f in dependencies+endpoints:
    wrapper=copy.deepcopy(f)
    if f.name not in keep:
        kws=[ast.keyword(arg=a.arg,value=ast.Name(id=a.arg,ctx=ast.Load())) for a in f.args.posonlyargs+f.args.args+f.args.kwonlyargs]
        call=ast.Call(func=ast.Attribute(value=ast.Name(id='service',ctx=ast.Load()),attr=f.name,ctx=ast.Load()),args=[],keywords=kws)
        no_body=any(any(k.arg=='status_code' and isinstance(k.value,ast.Constant) and k.value.value==204 for k in d.keywords) for d in f.decorator_list)
        docs=[copy.deepcopy(f.body[0])] if isinstance(f.body[0],ast.Expr) and isinstance(f.body[0].value,ast.Constant) and isinstance(f.body[0].value.value,str) else []
        wrapper.body=docs+([ast.Expr(value=call),ast.Return(value=ast.Call(func=ast.Name(id='Response',ctx=ast.Load()),args=[],keywords=[ast.keyword(arg='status_code',value=ast.Constant(value=204))]))] if no_body else [ast.Return(value=call)])
    api+='\n'+'\n'.join('    '+line for line in ast.unparse(ast.fix_missing_locations(wrapper)).splitlines())+'\n'
api+='\n    app.include_router(router)\n'
if domain=='devices':api+='    return device_auth\n'
repo='"""'+domain.title()+' SQL; transaction ownership is separate."""\n\nfrom .base import execute\n\n\nclass '+repo_class+':\n'
for q in queries:
    extra=''.join(', '+n for n in q['free'])
    repo+='    @staticmethod\n    def '+q['name']+'(db, parameters=()'+(', *'+extra if extra else '')+'):\n        return execute(db, '+q['statement']+', parameters)\n\n'
class Expected(ast.NodeTransformer):
    def visit(self,node):
        if isinstance(node,(ast.Call,ast.Name)) and hasattr(node,'lineno') and span(node) in rewrites:return copy.deepcopy(rewrites[span(node)])
        return super().visit(node)
actual_factory=next(n for n in ast.parse(service).body if isinstance(n,ast.FunctionDef) and n.name=='operations')
actual={n.name:n for n in actual_factory.body if isinstance(n,ast.FunctionDef)}
for original in business:
    expected=signature(Expected().visit(copy.deepcopy(original)))
    assert ast.dump(expected,include_attributes=False)==ast.dump(actual[original.name],include_attributes=False),original.name
for original in global_business:
    expected=Expected().visit(copy.deepcopy(original))
    actual_global=next(n for n in ast.parse(service).body if isinstance(n,type(original)) and n.name==original.name)
    assert ast.dump(expected,include_attributes=False)==ast.dump(actual_global,include_attributes=False),original.name
api_factory=next(n for n in ast.parse(api).body if isinstance(n,ast.FunctionDef) and n.name=='install_routes')
actual_api={n.name:n for n in api_factory.body if isinstance(n,ast.FunctionDef)}
for original in dependencies+endpoints:
    assert ast.dump(actual_api[original.name].args)==ast.dump(original.args)
    assert [ast.dump(n) for n in actual_api[original.name].decorator_list]==[ast.dump(n) for n in original.decorator_list]
    if original.name in keep:assert ast.dump(actual_api[original.name],include_attributes=False)==ast.dump(original,include_attributes=False)
if domain=='templates':
    api=api.replace('from ..services.templates import operations\n','from ..services.templates import operations, clean_config as _clean_config\nfrom ..core.errors import ServiceError\n')
    api+='\ndef clean_config(config):\n    \"\"\"Compatibility HTTP boundary for existing in-process template callers.\"\"\"\n    try:\n        return _clean_config(config)\n    except ServiceError as error:\n        raise HTTPException(error.status_code,error.detail,headers=error.headers) from None\n'
for filename,text in [(f'backend/api/{domain}.py',api),(f'backend/services/{domain}.py',service),(f'backend/repositories/{domain}.py',repo)]:
    ast.parse(text);(root/filename).write_text(text)
shim='"""Compatibility import retained during the three-layer extraction."""\n\nfrom .api.'+domain+' import install_routes as '+install_name+'\n'
if domain=='templates':shim+='from .api.templates import clean_config as clean_config\n'
if domain in ('templates','notifications','devices'):
    exports=[target.id for n in tree.body if isinstance(n,ast.Assign) for target in n.targets if isinstance(target,ast.Name) and target.id.isupper()]
    exports += [n.name for n in global_business if isinstance(n,ast.ClassDef)]
    if domain=='notifications':exports += ['_stamp','_epoch']
    if exports:shim+='from .services.'+domain+' import '+', '.join(name+' as '+name for name in exports)+'\n'
if domain=='history':shim+='from .services.history import DEVICE_EVENTS as DEVICE_EVENTS, message as message, severity as severity\n'
if projection_text:(root/'backend/db/projections.py').write_text(projection_text)
if domain=='devices':
    exports=json.loads((root/'.scratch/review-2026-11/B2/device-model-exports.json').read_text())
    shim='\"\"\"Compatibility exports for CPU device control during extraction.\"\"\"\n\nfrom .core.device_models import '+', '.join(name+' as '+name for name in exports)+'\nfrom .services.devices import AgentRuntime as AgentRuntime\nfrom .api.devices import install_routes as install_device_routes\n'
    old_all=next(n.value for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(a,ast.Name) and a.id=='__all__' for a in n.targets))
    shim+='\n__all__ = '+ast.unparse(old_all)+'\n'
(root/source_file).write_text(shim)
(root/f'.scratch/review-2026-11/B2/{domain}-ast-proof.json').write_text(json.dumps({'domain':domain,'sqlCalls':query_count,'businessFunctions':len(business),'httpFunctions':len(endpoints),'transportFunctionsKeptInAPI':sorted(keep),'businessAST':'same except repository/transaction calls, plain errors, dependency parameters/internal calls, HTTP response removal','httpSignaturesAndDecorators':'identical','queries':queries},indent=2)+'\n')
print(domain,': proved',len(business),'business bodies,',len(endpoints),'HTTP adapters,',query_count,'SQL calls')
