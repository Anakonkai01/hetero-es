"""Relocate study request contracts without changing any class AST."""
import ast
import json
from pathlib import Path
import subprocess

root=Path('/home/pc5070ti/projects/heteroes')
contracts={'study_registry':['ImportData','DatasetUpload','DatasetBuild','DatasetLimits','RegisterModel'],'model_qualification':['ProbeRequest']}
core='"""CPU-safe study and qualification request contracts."""\n\nfrom typing import Literal\nfrom pydantic import BaseModel, ConfigDict, Field\nfrom heteroes.noise.contracts import ENGINE_VERSION, ENGINE_V2\nfrom heteroes.product.model_qualification import STRICT_DECODER\nfrom .models import FiniteStrict\n'
proof=[]
prepared={}
for domain,names in contracts.items():
 source=subprocess.run(['git','show',f'96d662e7:backend/{domain}.py'],cwd=root,check=True,capture_output=True,text=True).stdout
 tree=ast.parse(source);lines=source.splitlines(keepends=True);classes=[n for n in tree.body if isinstance(n,ast.ClassDef) and n.name in names]
 assert len(classes)==len(names)
 for cls in classes:
  core+='\n\n'+ast.get_source_segment(source,cls)+'\n'
  proof.append({'class':cls.name,'module':domain,'AST':'identical'})
 for cls in reversed(classes):lines[cls.lineno-1:cls.end_lineno]=[]
 prepared[domain]='from .core.study_models import '+', '.join(names)+'\n'+''.join(lines)
actual=ast.parse(core)
for domain,names in contracts.items():
 source=subprocess.run(['git','show',f'96d662e7:backend/{domain}.py'],cwd=root,check=True,capture_output=True,text=True).stdout
 original={n.name:n for n in ast.parse(source).body if isinstance(n,ast.ClassDef)}
 for n in actual.body:
  if isinstance(n,ast.ClassDef) and n.name in names:assert ast.dump(n,include_attributes=False)==ast.dump(original[n.name],include_attributes=False)
(root/'backend/core/study_models.py').write_text(core)
for domain,text in prepared.items():(root/f'.scratch/review-2026-11/B2/{domain}-prepared.py').write_text(text)
(root/'.scratch/review-2026-11/B2/study-core-ast-proof.json').write_text(json.dumps({'base':'96d662e7','classes':proof},indent=2)+'\n')
print('Proved',len(proof),'unchanged study/qualification contracts')
