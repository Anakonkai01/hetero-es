import ast,json
from pathlib import Path
out=Path(__file__).parent
changed=[];unresolved=[]
for config in sorted(Path('acceptance/mutants').glob('*-backend.json')):
 original=config.read_text();mutants=json.loads(original);results=[]
 for mutant in mutants:
  oldfile=mutant['file'];name=mutant['name']
  if oldfile=='backend/model_qualification.py':newfile='backend/core/study_models.py' if name=='probe request accepts any decoder' else 'backend/services/model_qualification.py'
  elif oldfile=='backend/constants.py':newfile='backend/core/constants.py'
  else:newfile=oldfile.replace('backend/','backend/services/',1)
  target=Path(newfile);source=target.read_text();old=mutant['old'].replace('raise HTTPException(', 'raise ServiceError(');new=mutant['new'].replace('raise HTTPException(', 'raise ServiceError(')
  candidates=[]
  for delta in range(-24,25):
   def shift(text):
    lines=[]
    for line in text.splitlines(keepends=True):
     if not line.strip():lines.append(line);continue
     spaces=len(line)-len(line.lstrip(' '))
     if spaces==0:lines.append(line);continue
     if spaces+delta<0:return None
     lines.append(' '*(spaces+delta)+line[spaces:])
    return ''.join(lines)
   a,b=shift(old),shift(new)
   if a is not None and b is not None and source.count(a)==1:
    position=source.find(a)
    if old.startswith(" ") and position>0 and source[position-1]!="\n":continue
    try:ast.parse(source.replace(a,b,1))
    except SyntaxError:continue
    if (a,b) not in candidates:candidates.append((a,b))
  if len(candidates)!=1:
   unresolved.append({'config':config.name,'name':name,'target':newfile,'candidates':len(candidates)});continue
  a,b=candidates[0];mutant.update(file=newfile,old=a,new=b);results.append({'name':name,'beforeFile':oldfile,'afterFile':newfile})
 if any(r['config']==config.name for r in unresolved):continue
 (out/(config.stem+'-before.json')).write_text(original)
 config.write_text(json.dumps(mutants,indent=2)+'\n');changed.extend(results)
(out/'mutant-migration-report.json').write_text(json.dumps({'changed':changed,'unresolved':unresolved},indent=2)+'\n')
print(json.dumps({'changed':len(changed),'unresolved':unresolved},indent=2))
