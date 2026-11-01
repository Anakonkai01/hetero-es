"""Compare SQL expression definitions before/after B2 independently of extraction helpers."""
import ast
from collections import Counter
import hashlib
import json
from pathlib import Path
import subprocess

root=Path('/home/pc5070ti/projects/heteroes');base='6ee47147'
paths=subprocess.run(['git','ls-tree','-r','--name-only',base,'backend'],cwd=root,check=True,capture_output=True,text=True).stdout.splitlines()

def collect(files):
    corpus=Counter();locations={}
    for path,source in files:
        if path=='backend/repositories/base.py':continue # generic forwarding, not a SQL definition
        for node in ast.walk(ast.parse(source)):
            if not isinstance(node,ast.Call):continue
            expression=None
            if isinstance(node.func,ast.Attribute) and node.func.attr in {'execute','executemany','executescript'} and node.args:
                expression=node.args[0]
            elif isinstance(node.func,ast.Name) and node.func.id=='execute' and len(node.args)>=2:
                expression=node.args[1]
            if expression is not None:
                key=ast.dump(expression,include_attributes=False)
                corpus[key]+=1;locations.setdefault(key,[]).append({'path':path,'line':node.lineno,'expression':ast.unparse(expression)})
    return corpus,locations

old_files=[]
for name in paths:
    if name.endswith('.py') and 'tests' not in Path(name).parts:
        old_files.append((name,subprocess.run(['git','show',f'{base}:{name}'],cwd=root,check=True,capture_output=True,text=True).stdout))
new_files=[(str(p.relative_to(root)),p.read_text()) for p in sorted((root/'backend').rglob('*.py')) if 'tests' not in p.relative_to(root).parts]
old,old_locations=collect(old_files);new,new_locations=collect(new_files)
removed=set(old)-set(new);added=set(new)-set(old)
receipt={'base':base,'oldCalls':sum(old.values()),'newDefinitions':sum(new.values()),'oldUnique':len(old),'newUnique':len(new),'removed':[old_locations[k] for k in sorted(removed)],'added':[new_locations[k] for k in sorted(added)],'multiplicityChanges':[{'expression':old_locations.get(k,new_locations.get(k))[0]['expression'],'before':old[k],'after':new[k]} for k in sorted(set(old)&set(new)) if old[k]!=new[k]],'scope':'AST-equal SQL expressions; excludes generic repository forwarding; does not prove PostgreSQL portability or parameter/transaction behavior'}
(root/'.scratch/review-2026-11/B2/sql-corpus-proof.json').write_text(json.dumps(receipt,indent=2)+'\n')
print(json.dumps({k:v for k,v in receipt.items() if k not in {'removed','added','multiplicityChanges'}},indent=2))
print('removed expressions:',len(removed),'added:',len(added),'multiplicity changes:',len(receipt['multiplicityChanges']))
if removed or added:print(json.dumps({'removed':receipt['removed'],'added':receipt['added']},indent=2))
