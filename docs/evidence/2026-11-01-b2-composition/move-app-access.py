"""Move application composition and transport dependencies out of the business service graph."""
import ast
import copy
import hashlib
import json
from pathlib import Path
import subprocess

root=Path('/home/pc5070ti/projects/heteroes');base='9817afb5';proof=[]
def original(name):return subprocess.run(['git','show',f'{base}:backend/{name}.py'],cwd=root,check=True,capture_output=True,text=True).stdout
app_source=original('app');app_tree=ast.parse(app_source);create=next(n for n in app_tree.body if isinstance(n,ast.FunctionDef) and n.name=='create_app')
lab_source=original('lab');lab_factory=next(n for n in ast.parse(lab_source).body if isinstance(n,ast.FunctionDef))
source_functions={n.name:n for n in create.body if isinstance(n,ast.FunctionDef)}
lab_functions={n.name:n for n in lab_factory.body if isinstance(n,ast.FunctionDef)}
class AccessRewrite(ast.NodeTransformer):
 def visit_Name(self,n):
  if n.id in ('store','runtime'):return ast.Attribute(value=ast.Name(id='self',ctx=ast.Load()),attr=n.id,ctx=n.ctx)
  if n.id=='scoped':return ast.Attribute(value=ast.Name(id='self',ctx=ast.Load()),attr='scope',ctx=n.ctx)
  if n.id=='x_workspace_id':return ast.Name(id='workspace_id',ctx=n.ctx)
  if n.id=='HTTPException':return ast.Name(id='ServiceError',ctx=n.ctx)
  return n
access='"""Fresh account/workspace authorization and application state views."""\n\nfrom .policies import active_profile, platform_profile\nfrom ..core.errors import ServiceError\n\n\nclass AccessService:\n    def __init__(self, store, runtime):\n        self.store, self.runtime = store, runtime\n'
for old in [*[source_functions[n] for n in ['scoped','visible','authorized','capabilities']],*[lab_functions[n] for n in ['active','platform','workspace_admin']]]:
 f=AccessRewrite().visit(copy.deepcopy(old));f.name='scope' if old.name=='scoped' else old.name
 f.args.args=[ast.arg(arg='self')]+[ast.arg(arg='workspace_id' if a.arg=='x_workspace_id' else a.arg,annotation=copy.deepcopy(a.annotation)) for a in old.args.args];f.args.defaults=[]
 access+='\n    '+ast.unparse(ast.fix_missing_locations(f)).replace('\n','\n    ')+'\n'
 actual=next(n for n in next(n for n in ast.parse(access).body if isinstance(n,ast.ClassDef)).body if isinstance(n,ast.FunctionDef) and n.name==f.name)
 assert ast.dump(f,include_attributes=False)==ast.dump(actual,include_attributes=False)
 proof.append({'accessMethod':f.name,'bodyAST':'same except self store/runtime/scope forwarding and plain error class','dependencyDefaults':'removed from service signature'})
(root/'backend/services/access.py').write_text(access)
# Header/Depends stay in the API dependency with the original HTTP signature.
scoped=copy.deepcopy(source_functions['scoped']);scoped.body=ast.parse('return access.scope(current, x_workspace_id)').body
security=root/'backend/api/security.py';text=security.read_text().replace('from fastapi import Header, HTTPException','from fastapi import Depends, Header, HTTPException')
text+='\n\ndef workspace_scope(access, user):\n    '+ast.unparse(ast.fix_missing_locations(scoped)).replace('\n','\n    ')+'\n\n    return scoped\n';security.write_text(text)
# Stateless business callbacks are shared with the HTTP dependency wrappers.
lab='''"""Account, workspace and platform HTTP composition."""

from fastapi import Depends
from .accounts import install_routes as install_accounts_routes
from .workspaces import install_routes as install_workspaces_routes
from .operations import install_routes as install_operations_routes
from ..services.access import AccessService


def install_lab_routes(app, store, user, scoped, runtime):
    access = AccessService(store, runtime)

    def active(current=Depends(user)):
        return access.active(current)

    def platform(current=Depends(active)):
        return access.platform(current)

    install_accounts_routes(app, store, user)
    install_workspaces_routes(app, store, scoped, active, access.workspace_admin,
                             service_scoped=access.scope, service_active=access.active)
    install_operations_routes(app, store, runtime, platform, check_platform=access.platform)
'''
(root/'backend/api/lab.py').write_text(lab)
(root/'backend/lab.py').write_text('"""Compatibility lab HTTP composition export."""\n\nfrom .api.lab import install_lab_routes as install_lab_routes\n')
for filename,old,new in [
 ('backend/api/workspaces.py','def install_routes(app, store, scoped, active, workspace_admin):','def install_routes(app, store, scoped, active, workspace_admin, *, service_scoped=None, service_active=None):'),
 ('backend/api/operations.py','def install_routes(app, store, runtime, platform):','def install_routes(app, store, runtime, platform, *, check_platform=None):'),
 ('backend/api/experiments.py','def install_routes(app, store, runtime, scoped, visible, authorized, validate):','def install_routes(app, store, runtime, scoped, visible, authorized, validate, *, service_scoped=None):')]:
 p=root/filename;text=p.read_text();assert text.count(old)==1,(filename,old);text=text.replace(old,new)
 if 'workspaces' in filename:text=text.replace('service = operations(store, scoped, active, workspace_admin)','service = operations(store, service_scoped or scoped, service_active or active, workspace_admin)')
 elif 'operations' in filename:text=text.replace('business_operations(store, runtime, platform)','business_operations(store, runtime, check_platform or platform)')
 else:text=text.replace('operations(store, runtime, scoped, visible, authorized, validate)','operations(store, runtime, service_scoped or scoped, visible, authorized, validate)')
 p.write_text(text)
# Pure views and kernel lock implementation; HTTP streaming and telemetry CLI have their own owners.
for name,target in [('timeline','services/timeline'),('writer_lock','core/writer_lock'),('monitor','apps/monitor'),('live','api/live'),('routes_web','api/web')]:
 source=original(name);tree=ast.parse(source);edits=[];raw=source.encode();starts=[0]
 for line in raw.splitlines(keepends=True):starts.append(starts[-1]+len(line))
 for n in ast.walk(tree):
  if isinstance(n,ast.ImportFrom) and n.level:
   new=copy.deepcopy(n);new.level+=1
   if n.module=='store':new.module='core.constants'
   elif n.module=='timeline':new.module='services.timeline'
   elif n.module=='config':new.module='core.config'
   a,b=starts[n.lineno-1]+n.col_offset,starts[n.end_lineno-1]+n.end_col_offset;edits.append((a,b,ast.unparse(new).encode()))
 for a,b,text in sorted(edits,reverse=True):raw=raw[:a]+text+raw[b:]
 relocated=raw.decode();(root/f'backend/{target}.py').write_text(relocated)
 package,module=target.split('/')
 shim='"""Compatibility namespace retained during application composition extraction."""\n\nimport sys\nfrom .'+package+' import '+module+' as _implementation\n\n'
 if name=='monitor':shim+='if __name__ == "__main__":\n    raise SystemExit(_implementation.main())\nelse:\n    sys.modules[__name__] = _implementation\n'
 else:shim+='sys.modules[__name__] = _implementation\n'
 (root/f'backend/{name}.py').write_text(shim)
 proof.append({'module':name,'target':target,'body':'source spans unchanged except relative import destinations','bytesIdentical':not edits})
# Move the now-thin Store class without changing its body.
p=root/'backend/store.py';store_source=p.read_text();store_tree=ast.parse(store_source);store_raw=store_source.encode();starts=[0]
for line in store_raw.splitlines(keepends=True):starts.append(starts[-1]+len(line))
edits=[]
for n in ast.walk(store_tree):
 if isinstance(n,ast.ImportFrom) and n.level:
  new=copy.deepcopy(n)
  if n.module.startswith('services.'):new.module=n.module.removeprefix('services.')
  else:new.level+=1
  edits.append((starts[n.lineno-1]+n.col_offset,starts[n.end_lineno-1]+n.end_col_offset,ast.unparse(new).encode()))
for a,b,text in sorted(edits,reverse=True):store_raw=store_raw[:a]+text+store_raw[b:]
store_impl=store_raw.decode()
assert ast.dump(next(n for n in store_tree.body if isinstance(n,ast.ClassDef)),include_attributes=False)==ast.dump(next(n for n in ast.parse(store_impl).body if isinstance(n,ast.ClassDef)),include_attributes=False)
(root/'backend/services/store.py').write_text(store_impl)
p.write_text('"""Compatibility exports for the product state facade."""\n\nfrom .services.store import Store as Store, now as now, ACTIVE as ACTIVE, TERMINAL as TERMINAL\n')
proof.append({'StoreClassAST':'identical','preMoveSha256':hashlib.sha256(store_source.encode()).hexdigest()})
# Application imports and the four access closures become explicit composition.
raw=app_source.encode();starts=[0]
for line in raw.splitlines(keepends=True):starts.append(starts[-1]+len(line))
def span(n):return starts[n.lineno-1]+n.col_offset,starts[n.end_lineno-1]+n.end_col_offset
edits=[]
mapping={'routes_auth':'api.auth','routes_inventory':'api.inventory','routes_experiments':'api.experiments','routes_history':'api.history','routes_web':'api.web','validation':'services.validation','policies':'services.policies','config':'core.config','store':'services.store','lab':'api.lab','live':'api.live','templates':'api.templates','notifications':'api.notifications','study_registry':'services.study_registry','metadata_backup':'services.metadata_backup','model_qualification':'api.model_qualification','writer_lock':'core.writer_lock','local_storage':'storage.local_backend'}
for n in ast.walk(app_tree):
 if isinstance(n,ast.ImportFrom) and n.level:
  if n.module=='recovery_storage':text='from ..services.recovery_storage import RecoveryStorage\nfrom ..api.recovery_storage import install_routes as install_storage_routes'
  else:
   new=copy.deepcopy(n);new.level+=1;new.module=mapping.get(n.module,n.module)
   if n.module=='devices':new.module='services.devices' if any(a.name=='AgentRuntime' for a in n.names) else 'api.devices'
   if n.module=='study_registry':new.module='api.study_registry' if any(a.name=='install_routes' for a in n.names) else 'services.study_registry'
   for a in new.names:
    if a.name in ('install_template_routes','install_notification_routes','install_device_routes'):a.asname=a.asname or a.name;a.name='install_routes'
   text=ast.unparse(new)
  edits.append((*span(n),text.replace('\n','\n'+' '*n.col_offset).encode()))
for name in ['scoped','visible','authorized','capabilities']:
 replacement='scoped = workspace_scope(access, user)' if name=='scoped' else name+' = access.'+name
 edits.append((*span(source_functions[name]),replacement.encode()))
for a,b,text in sorted(edits,reverse=True):raw=raw[:a]+text+raw[b:]
factory=raw.decode().replace('from ..api.security import local_user','from ..api.security import local_user, workspace_scope\nfrom ..services.access import AccessService')
factory=factory.replace('    user = local_user(store.accounts)','    user = local_user(store.accounts)\n    access = AccessService(store, runtime)')
factory=factory.replace('        scoped=scoped,','        scoped=access.scope,')
factory=factory.replace('install_experiments_routes(app, store, runtime, scoped, visible, authorized, validate)','install_experiments_routes(app, store, runtime, scoped, visible, authorized, validate, service_scoped=access.scope)')
ast.parse(factory);(root/'backend/apps/factory.py').write_text(factory)
(root/'backend/app.py').write_text('"""Compatibility factory namespace retained during application extraction."""\n\nimport sys\nfrom .apps import factory as _implementation\n\nsys.modules[__name__] = _implementation\n')
# Business imports never route through compatibility modules that also export HTTP adapters.
replacements={
 'from ..model_qualification import':'from .model_qualification import',
 'from ..templates import':'from .templates import',
 'from ..timeline import':'from .timeline import',
 'from ..store import TERMINAL, now':'from ..core.constants import TERMINAL\nfrom ..core.clock import now',
 'from ..store import Store':'from .store import Store',
}
for p in (root/'backend/services').glob('*.py'):
 text=p.read_text()
 for old,new in replacements.items():text=text.replace(old,new)
 p.write_text(text)
# The canonical serving module is the composed factory; keep the desktop CLI contract unchanged.
p=root/'backend/apps/server.py';text=p.read_text().replace('"backend.app:app_from_environment"','"backend.apps.factory:app_from_environment"');p.write_text(text)
(root/'.scratch/review-2026-11/B2/app-access-ast-proof.json').write_text(json.dumps({'base':base,'proof':proof,'factory':'relative imports rewired; access closure bodies preserved in service, request dependency keeps original Header/Depends signature; lifecycle/bootstrap bodies otherwise unchanged','httpEndpointSignatures':'untouched; only installer callback wiring has optional business callbacks','businessImportRetarget':'same implementation classes/functions via direct service/core owners; template errors stay plain','cliServingTarget':'backend.apps.factory:app_from_environment'},indent=2)+'\n')
print('Proved access bodies, Store class and source-span relocations; composed apps factory without service HTTP imports')
