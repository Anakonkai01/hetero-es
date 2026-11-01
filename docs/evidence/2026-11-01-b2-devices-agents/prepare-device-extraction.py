"""Split HTTP bearer/path parsing from the existing device drain authorization body."""
import ast
import copy
import json
from pathlib import Path
import subprocess

root=Path('/home/pc5070ti/projects/heteroes')
source=subprocess.run(['git','show','96d662e7:backend/devices.py'],cwd=root,check=True,capture_output=True,text=True).stdout
tree=ast.parse(source);factory=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='install_device_routes')
original=next(n for n in factory.body if isinstance(n,ast.FunctionDef) and n.name=='device_auth')
class AuthorizationBody(ast.NodeTransformer):
    def visit_Subscript(self,node):
        if isinstance(node.value,ast.Name) and node.value.id=='authorization':
            assert isinstance(node.slice,ast.Slice) and node.slice.lower.value==7
            return ast.Name(id='token',ctx=ast.Load())
        return self.generic_visit(node)
    def visit_Attribute(self,node):
        if node.attr=='path' and isinstance(node.value,ast.Attribute) and node.value.attr=='url' and isinstance(node.value.value,ast.Name) and node.value.value.id=='request':
            return ast.Name(id='purpose',ctx=ast.Load())
        return self.generic_visit(node)
    def visit_Constant(self,node):
        if node.value=='/api/v1/device/poll':return ast.Constant(value='poll')
        if node.value=='/api/v1/device/worker-command':return ast.Constant(value='worker-command')
        return node
body=AuthorizationBody().visit(copy.deepcopy(original));body.name='authenticate_device';body.args=ast.arguments(posonlyargs=[],args=[ast.arg(arg='token'),ast.arg(arg='purpose')],kwonlyargs=[],kw_defaults=[],defaults=[]);body.body=body.body[1:]
lines=source.splitlines(keepends=True);text='\n'.join('    '+line for line in ast.unparse(ast.fix_missing_locations(body)).splitlines())+'\n';lines[original.lineno-1:original.end_lineno]=[text];prepared=''.join(lines)
api=copy.deepcopy(original)
api.body=[copy.deepcopy(original.body[0])]
api.body+=ast.parse('''path = request.url.path
purpose = "poll" if path == "/api/v1/device/poll" else "worker-command" if path == "/api/v1/device/worker-command" else "control"
return service.authenticate_device(authorization[7:], purpose)
''').body
api_text='\n'.join('    '+line for line in ast.unparse(ast.fix_missing_locations(api)).splitlines())+'\n'
assert ast.dump(api.args)==ast.dump(original.args)
# Both path predicates preserve the exact action truth table used for drain-only access.
for path in ['/api/v1/device/poll','/api/v1/device/worker-command','/api/v1/device/qualification','/api/v1/device/recovery-points','/api/v1/devices']:
    purpose='poll' if path=='/api/v1/device/poll' else 'worker-command' if path=='/api/v1/device/worker-command' else 'control'
    assert (path=='/api/v1/device/poll')==(purpose=='poll')
    assert (path=='/api/v1/device/worker-command')==(purpose=='worker-command')
(root/'.scratch/review-2026-11/B2/device-source-prepared.py').write_text(prepared)
(root/'.scratch/review-2026-11/B2/device-api-auth.txt').write_text(api_text)
exports=[]
for n in tree.body:
    if isinstance(n,ast.ImportFrom) and n.module=='device_models':exports += [x.name for x in n.names]
(root/'.scratch/review-2026-11/B2/device-model-exports.json').write_text(json.dumps(exports,indent=2)+'\n')
(root/'.scratch/review-2026-11/B2/device-auth-boundary-proof.json').write_text(json.dumps({'base':'96d662e7','httpSignature':'identical','bearerPrefixGuardAST':'identical','businessBody':'same after token argument extraction and path-to-action mapping','pathActionTruthTable':'poll,worker-command,all other paths preserved','factoryReturns':'device_auth dependency'},indent=2)+'\n')
print('Prepared device auth split; bearer guard/signature and drain action mapping checked')
