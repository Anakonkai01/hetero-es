"""Restore the original HTTP signatures around the prepared transport-independent recovery service."""
import ast
import copy
import json
from pathlib import Path
import sys

root=Path('/home/pc5070ti/projects/heteroes');output=Path(sys.argv[1]) if len(sys.argv)>1 else root
scratch=root/'.scratch/review-2026-11/B2'
p=output/'backend/api/recovery_storage.py';source=p.read_text();raw=source.encode();starts=[0]
for line in raw.splitlines(keepends=True):starts.append(starts[-1]+len(line))
def span(n):return starts[n.lineno-1]+n.col_offset,starts[n.end_lineno-1]+n.end_col_offset
factory=next(n for n in ast.parse(source).body if isinstance(n,ast.FunctionDef) and n.name=='install_routes')
functions={n.name:n for n in factory.body if isinstance(n,ast.FunctionDef)}
overrides=ast.parse((scratch/'recovery-http-overrides.py').read_text()).body
edits=[]
for node in overrides:
 new=copy.deepcopy(node);new.decorator_list=[]
 edits.append((*span(functions[node.name]),ast.unparse(ast.fix_missing_locations(new)).replace('\n','\n    ').encode()))
for a,b,text in sorted(edits,reverse=True):raw=raw[:a]+text+raw[b:]
source=raw.decode();actual_factory=next(n for n in ast.parse(source).body if isinstance(n,ast.FunctionDef) and n.name=='install_routes')
actual={n.name:n for n in actual_factory.body if isinstance(n,ast.FunctionDef)}
proof=json.loads((scratch/'recovery-boundary-proof.json').read_text())
for node in overrides:
 assert ast.dump(actual[node.name],include_attributes=False)==ast.dump(node,include_attributes=False),node.name
 assert ast.dump(actual[node.name].args,include_attributes=False)==proof['originalHttpArgs'][node.name]
 assert [ast.dump(n,include_attributes=False) for n in actual[node.name].decorator_list]==proof['originalDecorators'][node.name]
p.write_text(source)
print('Proved original ticket/consume HTTP signatures, cookie operations and redirect headers')
