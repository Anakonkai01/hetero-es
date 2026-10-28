"""Create portable frozen files and exact adapter bytes once on CPU, never during GPU timing."""
import hashlib
import json
import os
from pathlib import Path
import platform
import struct

if os.environ.get('CUDA_VISIBLE_DEVICES') != '':
    raise RuntimeError('CPU-only bundle preparation')
import torch
import numpy
from heteroes.es.perturb import perturb_model_
from heteroes.es.snapshot import take_snapshot, restore_from_snapshot_, diff_from_snapshot
from heteroes.eval.frozen_int8 import identity
from heteroes.model.frozen_int8 import freeze_projections, freeze_tied_head, frozen_modules, create_initial_frozen_adapter
from heteroes.model.lora import trainable_schema
from heteroes.noise.contracts import ENGINE_V2
from heteroes.v3.model import load, file_manifest

HERE=Path(__file__).resolve().parent
OUT=HERE/'bundles'
OUT.mkdir(exist_ok=False)
for key in ('smol','qwen','tiny'):
    parent=Path('/home/pc5070ti/projects/heteroes/.scratch/strict-integer-20261025/models')/key
    target=OUT/key
    target.mkdir()
    files=file_manifest(parent)
    model,_=load(parent,files,'cpu')
    frozen=freeze_projections(model,rank=8,alpha=16.,seed=1234,artifact_directory=target/'projections')
    head=None
    if model.lm_head.weight is model.model.embed_tokens.weight:
        head=freeze_tied_head(model,artifact_path=target/'head.fint8')
    schema=trainable_schema(model)
    adapters={}
    def save(label):
        path=target/(label+'.bin')
        adapters[label]={'path':path.name,'sha256':create_initial_frozen_adapter(model,path),'bytes':path.stat().st_size}
    save('zero')
    generator=torch.Generator().manual_seed(1234)
    with torch.no_grad():
        for _,module in frozen_modules(model):
            weight=torch.empty(module.lora_B[module.adapter_name].weight.shape,dtype=torch.float32)
            weight.normal_(0.,0.02,generator=generator)
            module.lora_B[module.adapter_name].weight.copy_(weight)
    save('probe')
    snapshot=take_snapshot(model,schema)
    for label,sigma in (('plus',1e-3),('minus',-1e-3)):
        perturb_model_(model,schema,7001,sigma,engine=ENGINE_V2)
        save(label)
        restore_from_snapshot_(model,schema,snapshot)
        assert diff_from_snapshot(model,schema,snapshot)==[]
    actual={p.relative_to(target).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in target.rglob('*') if p.is_file()}
    data={'format':'heteroes.frozen-perf-bundle.v1','modelKey':key,'parentFiles':files,'frozenArtifacts':frozen,
          'headArtifact':head,'headVariant':'int8-tied-sidecar' if head else 'strict-fp16-untied',
          'operatorIdentity':identity(),'rank':8,'alpha':16.,'scaleFP32Bits':struct.pack('<f',2.).hex(),
          'adapterSeed':1234,'schema':schema.to_dict(),'schemaHash':schema.hash,'adapters':adapters,
          'candidate':{'engine':ENGINE_V2,'seed':7001,'sigma':1e-3,'parent':'probe','labels':['plus','minus']},
          'files':actual,'environment':{'python':platform.python_version(),'torch':torch.__version__,'numpy':numpy.__version__}}
    data['bundleSha256']=hashlib.sha256(json.dumps(data,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode()).hexdigest()
    with (target/'manifest.json').open('x') as f:json.dump(data,f,indent=2);f.write('\n')
    print(key,data['bundleSha256'],len(frozen),'projections',flush=True)
    del model
