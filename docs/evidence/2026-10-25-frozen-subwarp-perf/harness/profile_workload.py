"""Profile the benchmark loader and its exact tokenized workload; no independent prompt list."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
from collections import Counter

parser = argparse.ArgumentParser()
parser.add_argument('--model', required=True)
parser.add_argument('--out', type=Path, required=True)
parser.add_argument('--batch', type=int, default=32)
parser.add_argument('--gpu', action='store_true')
args = parser.parse_args()
if args.out.exists():
    parser.error('Existing evidence')
if not args.gpu or os.environ.get('HETEROES_GPU_ACCEPTANCE') != '1':
    parser.error('GPU opt-in required')
import torch
from torch.profiler import profile, ProfilerActivity
root = Path.cwd()
spec=importlib.util.spec_from_file_location('benchmark',root/'runtime/scripts/benchmark_inference.py')
bench=importlib.util.module_from_spec(spec)
spec.loader.exec_module(bench)
model=Path('/home/pc5070ti/projects/heteroes/.scratch/strict-integer-20261025/models')/args.model
config=json.loads((model/'config.json').read_text())
options=argparse.Namespace(engine='strict-frozen',model_path=model,max_new_tokens=32,max_context=512,
    graph_max_bytes=4*1024**3,lora_rank=8,lora_alpha=16.,adapter_seed=1234,nonzero_adapter=False,
    frozen_head=bool(config.get('tie_word_embeddings',False)),decode_ctas_per_sm=8,hf_chunk=0)
report={'environment':{}}
engine,prompts,run=bench.load_engine(options,report)
names={id(module):name for name,module in engine.model.named_modules()}
calls=[]
for method in ('_adapter_middle','_adapter_finish'):
    old=getattr(engine,method)
    def wrapped(*items,_method=method,_old=old):
        value=items[0]; module=items[1] if _method=='_adapter_middle' else items[2]
        calls.append((_method,names[id(module)],value.numel()//value.shape[-1],value.shape[-1],module.out_features))
        return _old(*items)
    setattr(engine,method,wrapped)
selected=[prompts[i%len(prompts)] for i in range(args.batch)]
run(selected)
torch.cuda.synchronize()
with profile(activities=[ProfilerActivity.CPU,ProfilerActivity.CUDA],record_shapes=False) as prof:
    output=run(selected)
    torch.cuda.synchronize()
events=[]
for event in prof.key_averages():
    duration=event.self_device_time_total
    if duration:
        events.append({'key':event.key,'selfCudaUs':duration,'calls':event.count})
events.sort(key=lambda e:e['selfCudaUs'],reverse=True)
report.update(batch=args.batch,events=events,adapterCallSites=[{'call':list(k),'count':v} for k,v in Counter(calls).items()],
              tokens=output,kernelIdentity=engine.kernel_identity())
with args.out.open('x') as f:json.dump(report,f,indent=2);f.write('\n')
print(prof.key_averages().table(sort_by='self_cuda_time_total',row_limit=20))
