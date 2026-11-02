import ast,importlib.util,json,shutil
from pathlib import Path
root=Path('/home/pc5070ti/projects/heteroes')
modules={}
keep={'__init__','server','doctor','monitor'}
moves={'passwords':'core.passwords','experiment_view':'services.experiment_view','runtime_sources':'core.runtime_sources'}
for path in sorted((root/'backend').glob('*.py')):
 if path.stem=='__init__':continue
 tree=ast.parse(path.read_text());symbols={};default=None
 if path.stem in moves:default='backend.'+moves[path.stem]
 for node in tree.body:
  if isinstance(node,ast.ImportFrom):
   base=importlib.util.resolve_name('.'*node.level+(node.module or ''),'backend') if node.level else node.module
   for name in node.names:
    if name.asname=='_implementation':default=base+'.'+name.name
    else:symbols[name.asname or name.name]=(base,name.name)
 modules['backend.'+path.stem]={'default':default,'symbols':symbols}
modules['backend.monitor']['default']='backend.apps.monitor'
modules['backend.doctor']['default']='backend.services.doctor'
changed=[]
paths=[*sorted((root/'backend').rglob('*.py')),*sorted((root/'scripts').glob('*.py'))]
for path in paths:
 if 'fixtures' in path.relative_to(root).parts:continue
 if path.parent==root/'backend' and path.stem!='__init__':continue
 text=path.read_text();tree=ast.parse(text);replacements=[]
 package='.'.join(path.relative_to(root).parts[:-1])
 for node in ast.walk(tree):
  if not isinstance(node,ast.ImportFrom):continue
  base=importlib.util.resolve_name('.'*node.level+(node.module or ''),package) if node.level else node.module
  if base in modules:
   groups={}
   for item in node.names:
    actual=modules[base]['symbols'].get(item.name)
    if actual is None:
     default=modules[base]['default'];assert default,(path,node.lineno,item.name)
     actual=(default,item.name)
    target,name=actual;binding=item.asname or item.name
    groups.setdefault(target,[]).append(name+(' as '+binding if binding!=name or item.asname else ''))
   rendered=('\n'+' '*node.col_offset).join('from '+target+' import '+', '.join(names) for target,names in groups.items())
   lines=text.splitlines(keepends=True);start=sum(len(s) for s in lines[:node.lineno-1])+node.col_offset;end=sum(len(s) for s in lines[:node.end_lineno-1])+node.end_col_offset
   replacements.append((start,end,rendered))
  elif base=='backend':
   groups={};affected=False
   for item in node.names:
    alias='backend.'+item.name
    if alias in modules and modules[alias]['default']:
     affected=True;target=modules[alias]['default'];parent,name=target.rsplit('.',1);binding=item.asname or item.name
     groups.setdefault(parent,[]).append(name+(' as '+binding if binding!=name or item.asname else ''))
    else:groups.setdefault(base,[]).append(item.name+(' as '+item.asname if item.asname else ''))
   if affected:
    rendered=('\n'+' '*node.col_offset).join('from '+target+' import '+', '.join(names) for target,names in groups.items())
    lines=text.splitlines(keepends=True);start=sum(len(s) for s in lines[:node.lineno-1])+node.col_offset;end=sum(len(s) for s in lines[:node.end_lineno-1])+node.end_col_offset
    replacements.append((start,end,rendered))
 for first,last,replacement in sorted(replacements,reverse=True):text=text[:first]+replacement+text[last:]
 if path.name=='test_shared_runtime.py':text=text.replace('import backend.monitor, backend.study_registry','import backend.monitor, backend.services.study_registry')
 if path.name=='test_writer_lock.py':text=text.replace('from backend.writer_lock import acquire_writer;','from backend.core.writer_lock import acquire_writer;')
 if path.name=='check-source-packages.py':
  text=text.replace('backend/errors.py','backend/core/errors.py').replace('from backend.app import create_app; from backend.errors import RuntimeRejected','from backend.apps.factory import create_app; from backend.core.errors import RuntimeRejected')
 if text!=path.read_text():ast.parse(text);path.write_text(text);changed.append(path.relative_to(root).as_posix())
for source,target in moves.items():
 old=root/'backend'/f'{source}.py';new=root/('backend/'+target.replace('.','/')+'.py');assert not new.exists();shutil.move(old,new)
removed=[]
for path in sorted((root/'backend').glob('*.py')):
 if path.stem not in keep:path.unlink();removed.append(path.name)
(root/'.scratch/review-2026-11/B9/shim-removal-map.json').write_text(json.dumps({'baseline':'e23a2963','modules':modules,'moved':moves,'removedPhysicalAliases':removed,'changedFiles':changed},indent=2)+'\n')
print('Rewrote',len(changed),'files; moved3 real helpers and removed',len(removed),'physical aliases')
