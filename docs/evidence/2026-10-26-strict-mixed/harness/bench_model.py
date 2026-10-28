"""Three execution variants share one primary model; new arithmetic, report differences explicitly."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import statistics

import torch
from heteroes.eval.integer_decoder import IntegerDecoderGraph
from heteroes.v3.model import file_manifest,load
from mixed_decoder import MixedDecoderGraph

p=argparse.ArgumentParser();p.add_argument('--gpu',action='store_true');p.add_argument('--model',required=True)
p.add_argument('--models-root',type=Path,required=True);p.add_argument('--benchmark',type=Path,required=True)
p.add_argument('--out',type=Path,required=True);a=p.parse_args()
if not a.gpu or os.environ.get('HETEROES_GPU_ACCEPTANCE')!='1' or a.out.exists():p.error('GPU opt-in and fresh output')
def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
bench=module('benchmark',a.benchmark);probe=module('probe',a.benchmark.with_name('probe_strict_backend.py'))
files=file_manifest(a.models_root/a.model);model,tokenizer=load(a.models_root/a.model,files,'cuda')
prompts=[tokenizer(text)['input_ids'] for text in probe.PROMPTS]
engines={'a22w22':IntegerDecoderGraph(model,magnitude_bits=22,max_context=512,max_graph_bytes=4*1024**3),
         'a22w6':MixedDecoderGraph(model,activation_bits=22,weight_bits=6,max_context=512,max_graph_bytes=4*1024**3),
         'a14w6':MixedDecoderGraph(model,activation_bits=14,weight_bits=6,max_context=512,max_graph_bytes=4*1024**3)}
runs={name:bench.decoder_run(e,pad=tokenizer.pad_token_id or 0,tokens=32) for name,e in engines.items()}
report={'gpu':torch.cuda.get_device_name(),'modelFiles':files,'promptTokenIds':prompts,'headPolicy':'unchanged_b22',
        'cases':[],'comparisons':[],'hardwareQualified':False}
for batch in (1,8,32):
    selected=[prompts[i%8] for i in range(batch)]
    actual={name:run(selected) for name,run in runs.items()}
    records=[]
    for name in ('a22w22','a22w6','a14w6','a14w6','a22w6','a22w22'):
        result=bench.measure(runs[name],selected,32,5,torch.cuda.synchronize)
        assert result['repeatTokensEqual'] and result['tokens']==actual[name]
        records.append({'variant':name,**result})
    raw={name:[t for r in records if r['variant']==name for t in r['seconds']] for name in engines}
    speeds={name:32*batch/statistics.median(times) for name,times in raw.items()}
    report['cases'].append({'batch':batch,'records':records})
    report['comparisons'].append({'batch':batch,'speeds':speeds,
                                  'ratios':{name:speed/speeds['a22w22'] for name,speed in speeds.items()},
                                  'rowsEqualB22':{name:sum(x==y for x,y in zip(actual['a22w22'],tokens)) for name,tokens in actual.items()}})
    print(a.model,report['comparisons'][-1],flush=True)
report['backendIdentities']={name:e.identity for name,e in engines.items()}
report['kernelIdentities']={name:e.kernel_identity() for name,e in engines.items()}
with a.out.open('x') as f:json.dump(report,f,indent=2);f.write('\n')
