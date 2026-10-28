import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import statistics
import time
p=argparse.ArgumentParser();p.add_argument('--gpu',action='store_true');p.add_argument('--bits',type=int,choices=[14,22],required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
assert a.gpu and os.environ.get('HETEROES_GPU_ACCEPTANCE')=='1' and not a.out.exists()
import torch
from heteroes.eval.integer_decoder import IntegerDecoderGraph
from captured_prefill import PrefillIntegerGraph
from heteroes.v3.model import load,file_manifest
spec=importlib.util.spec_from_file_location('benchmark','runtime/scripts/benchmark_inference.py');bench=importlib.util.module_from_spec(spec);spec.loader.exec_module(bench)
spec=importlib.util.spec_from_file_location('probe','runtime/scripts/probe_strict_backend.py');probe=importlib.util.module_from_spec(spec);spec.loader.exec_module(probe)
path=Path('/home/pc5070ti/projects/heteroes/.scratch/strict-integer-20261025/models/qwen');model,tok=load(path,file_manifest(path),'cuda')
engines={'eager':IntegerDecoderGraph(model,magnitude_bits=a.bits,max_context=512,max_graph_bytes=6*1024**3),'capture':PrefillIntegerGraph(model,magnitude_bits=a.bits,max_context=512,max_graph_bytes=6*1024**3)}
short=[tok(s)['input_ids'] for s in probe.PROMPTS];rows=[short[i%8] for i in range(32)]
report={'bits':a.bits,'gpu':torch.cuda.get_device_name(),'cases':[],'limits':'Unselected shape capture; parent only, no native/canonical-candidate qualification.'}
for n in (1,32):
 runs={name:bench.decoder_run(engine,pad=tok.pad_token_id or 0,tokens=n) for name,engine in engines.items()}
 expected={name:run(rows) for name,run in runs.items()};assert expected['eager']==expected['capture']
 count=engines['capture'].prefill_capture_count;times={name:[] for name in engines}
 for name in ('eager','capture','capture','eager'):
  for _ in range(4):
   torch.cuda.synchronize();start=time.perf_counter();actual=runs[name](rows);torch.cuda.synchronize();times[name].append(time.perf_counter()-start);assert actual==expected[name]
 assert engines['capture'].prefill_capture_count==count and all(not bool(t.any()) for t in engines['capture'].prefill_request_buffers())
 summary={name:{'seconds':values,'medianMs':statistics.median(values)*1000,'tokensPerSecond':32*n/statistics.median(values)} for name,values in times.items()}
 report['cases'].append({'tokens':n,'summary':summary,'captureCount':count});print(a.bits,n,json.dumps(summary),flush=True)
report['peakAllocatedBytes']=torch.cuda.max_memory_allocated()
with a.out.open('x') as f:json.dump(report,f,indent=2);f.write('\n')
