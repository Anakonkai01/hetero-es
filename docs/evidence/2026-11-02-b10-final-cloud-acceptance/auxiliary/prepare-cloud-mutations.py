import ast,json,hashlib
from pathlib import Path
root=Path('/home/pc5070ti/projects/heteroes');out=Path(__file__).parent
specs={'engine':'B3/engine-mutants.json','services':'B4/core-mutants.json','oidc':'B5/mutants.json','s3-config':'B6/config-mutants.json','s3-io':'B6/io-mutants.json'}
provenance={}
for kind,name in specs.items():
 p=out.parent/name;entries=json.loads(p.read_text());adapt=[]
 for m in entries:
  if kind=='services' and m['name']=='one failed job rolls back the whole scheduler tick':
   before=dict(m);m['old']='with leader.session():';m['new']='with leader.transaction():';adapt.append({'name':m['name'],'reason':'B7 added a second _leader.session substring; bind this original tick mutation to the full owning leader statement','before':before,'after':dict(m)})
  source=(root/m['file']).read_text();assert source.count(m['old'])==1,(kind,m['name']);ast.parse(source.replace(m['old'],m['new'],1))
 (out/(kind+'-mutants.json')).write_text(json.dumps(entries,indent=2)+'\n')
 provenance[kind]={'sourceConfig':name,'sourceSha256':hashlib.sha256(p.read_bytes()).hexdigest(),'count':len(entries),'adaptations':adapt}
(out/'cloud-mutant-provenance.json').write_text(json.dumps(provenance,indent=2)+'\n')
print('Validated current engine6,services16,OIDC25,S3config8 and S3IO21 targets')
