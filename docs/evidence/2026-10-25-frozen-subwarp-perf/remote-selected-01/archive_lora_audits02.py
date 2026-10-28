"""Archive the actual compiled LoRA PTX/SASS passed to the existing audits."""
import argparse
import hashlib
import json
import os
from pathlib import Path

parser=argparse.ArgumentParser()
parser.add_argument('--out',type=Path,required=True)
parser.add_argument('--gpu',action='store_true')
args=parser.parse_args()
if args.out.exists():parser.error('Existing evidence')
if not args.gpu or os.environ.get('HETEROES_GPU_ACCEPTANCE')!='1':parser.error('GPU opt-in')
from heteroes.eval import strict_cuda as sc
import torch
# The private compilation entrypoint assumes an active primary CUDA context; public operators allocate outputs first.
context_owner=torch.empty(1,device='cuda')
args.out.mkdir(parents=True)
label=''
for name,suffix in (('audit_ptx','ptx'),('audit_sass','sass')):
 original=getattr(sc,name)
 def wrapped(text,exact=(),_original=original,_suffix=suffix):
  (args.out/(label+'.'+_suffix)).write_text(text)
  return _original(text,exact)
 setattr(sc,name,wrapped)
k=sc.StrictCudaKernels('cuda')
for rank,execution in ((8,'warp'),(8,'output'),(16,'output'),(32,'warp')):
 label=f'rank{rank}-row8-{execution}-{k.arch}'
 k._lora_function(rank,8,execution)
report={'sourceSha256':hashlib.sha256(Path(sc.__file__).read_bytes()).hexdigest(),'identity':k.identity()}
with (args.out/'identity.json').open('x') as f:json.dump(report,f,indent=2);f.write('\n')
