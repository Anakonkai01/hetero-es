"""Reproduce the import, extracted-method and frozen-source checks against the handoff commit."""
import ast
import hashlib
import json
from pathlib import Path
import subprocess


REPO = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
BASE = '8f9ae95'


def before(path):
    return subprocess.check_output(['git', 'show', f'{BASE}:{path}'], cwd=REPO, text=True)


def parsed(path):
    return ast.parse((REPO / path).read_text())


def same(left, right):
    assert ast.dump(left) == ast.dump(right)


def methods(tree, name):
    cls = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == name)
    return {node.name: node for node in cls.body if isinstance(node, ast.FunctionDef)}


old_text = before('runtime/src/heteroes/product/gateway.py')
old_tree = ast.parse(old_text)
new_tree = parsed('runtime/src/heteroes/product/run_supervisor.py')
old = methods(old_tree, 'Manager')
new = methods(new_tree, 'RunSupervisor')
unchanged = ['directory', 'state', 'save', 'log', 'poll_workers', 'tick', 'loop', 'snapshot']
for name in unchanged:
    same(old[name], new[name])

# The removed cache belonged to the old gateway's worker registry. Maintenance
# holds belonged to its retired backup API. Neither is used by agent assignments.
expected_text = old_text.replace('        self.cache, self.cache_at = [], 0\n', '').replace(
    "            if read_json(self.root/'maintenance.json'):\n"
    "                raise RuntimeError('Runtime is held for maintenance')\n", '')
expected = methods(ast.parse(expected_text), 'Manager')
for name in ['__init__', 'submit']:
    same(expected[name], new[name])
assert set(new) == set(unchanged) | {'__init__', 'submit', 'launch', 'remote', 'start_worker'}
expected_validate = ast.parse(old_text.replace('capabilities(workers)["workloads"]', 'WORKLOADS'))
for name in ['iso', 'validate']:
    same(next(n for n in expected_validate.body if isinstance(n, ast.FunctionDef) and n.name == name),
         next(n for n in new_tree.body if isinstance(n, ast.FunctionDef) and n.name == name))
old_cap = next(n for n in old_tree.body if isinstance(n, ast.FunctionDef) and n.name == 'capabilities')
old_workloads = next(value for key, value in zip(old_cap.body[0].value.keys, old_cap.body[0].value.values)
                     if ast.literal_eval(key) == 'workloads')
new_workloads = next(n.value for n in new_tree.body if isinstance(n, ast.Assign)
                     and any(isinstance(t, ast.Name) and t.id == 'WORKLOADS' for t in n.targets))
assert list(ast.literal_eval(new_workloads)) == ast.literal_eval(old_workloads)
agent_expected = before('runtime/src/heteroes/product/agent.py').replace(
    'from .gateway import Manager,TERMINAL,QUIESCENT,ROOT,validate',
    'from .run_supervisor import RunSupervisor,TERMINAL,QUIESCENT,ROOT,validate').replace(
    'class AgentManager(Manager):', 'class AgentManager(RunSupervisor):')
same(ast.parse(agent_expected), parsed('runtime/src/heteroes/product/agent.py'))

store_old = methods(ast.parse(before('backend/store.py')), 'Store')['_dispatch_parallel']
store_old.name = '_dispatch_once'
same(store_old, methods(parsed('backend/store.py'), 'Store')['_dispatch_once'])

frozen = json.loads((OUT / 'frozen-source-sha256.json').read_text())
for path, digest in frozen.items():
    assert hashlib.sha256((REPO / path).read_bytes()).hexdigest() == digest
    original = subprocess.check_output(['git', 'show', f'{BASE}:{path}'], cwd=REPO)
    assert hashlib.sha256(original).hexdigest() == digest

src = REPO / 'runtime/src'
modules = {'.'.join(p.relative_to(src).with_suffix('').parts).removesuffix('.__init__'): p
           for p in src.rglob('*.py')}
graph = {}
for name, path in modules.items():
    edges = set()
    for node in ast.walk(ast.parse(path.read_text())):
        targets = []
        if isinstance(node, ast.Import):
            targets = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            parent = name.split('.')[:-1]
            base = '.'.join(parent[:len(parent) - node.level + 1]) if node.level else ''
            target = '.'.join(filter(None, [base, node.module]))
            targets = [target, *[target + '.' + alias.name for alias in node.names]]
        assert not {'heteroes.product.gateway', 'heteroes.product.backup'} & set(targets)
        edges.update(t for t in targets if t in modules)
    graph[name] = sorted(edges)
pending = ['heteroes.product.agent', 'heteroes.product.runner']
closure = set()
while pending:
    name = pending.pop()
    if name in closure:
        continue
    closure.add(name)
    pending.extend(graph.get(name, []))
assert {'heteroes.product.run_supervisor', 'heteroes.coordinator', 'heteroes.dispatch'} <= closure
(OUT / 'runtime-imports-after.json').write_text(json.dumps(
    {name: graph[name] for name in sorted(closure)}, indent=2) + '\n')
result = {'baseline': BASE, 'unchangedSupervisorMethodASTs': unchanged,
          'expectedSupervisorChanges': ['__init__: remove registry cache', 'submit: remove legacy maintenance hold'],
          'unchangedAgentASTExceptBaseImport': True, 'unchangedWorkloads': True,
          'unchangedDispatcherAST': True, 'unchangedNumericalFiles': len(frozen),
          'agentAndRunnerImportClosure': len(closure), 'retiredImports': []}
print(json.dumps(result, indent=2))
