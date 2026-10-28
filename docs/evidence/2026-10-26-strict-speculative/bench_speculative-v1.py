"""Whole-generation ABCCBA pilot over canonical FP16 candidates and parent-only proposals."""
import argparse
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import statistics
import time

p=argparse.ArgumentParser();p.add_argument('--gpu',action='store_true');p.add_argument('--out',type=Path,required=True)
p.add_argument('--batches',type=int,nargs='+',choices=(1,8),default=[1,8])
p.add_argument('--states',nargs='+',choices=('parent','plus','minus'),default=['parent','plus','minus'])
p.add_argument('--repeats',type=int,default=5)
a=p.parse_args()
if not a.gpu or os.environ.get('HETEROES_GPU_ACCEPTANCE')!='1' or a.out.exists():p.error('GPU opt-in/fresh output required')
import torch
from heteroes.es.perturb import perturb_model_
from heteroes.es.snapshot import restore_from_snapshot_,take_snapshot
from heteroes.eval.candidate import model_weights_sha256
from heteroes.eval.integer_decoder import IntegerDecoderGraph
from heteroes.model.schema import build_parameter_schema
from heteroes.noise.contracts import ENGINE_V2
from heteroes.v3.model import load,file_manifest
from speculative import SpeculativeGraph,SuffixProposer

def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result);return result
bench=module('benchmark','runtime/scripts/benchmark_inference.py')
path=Path('/home/pc5070ti/projects/heteroes/.scratch/strict-integer-20261025/models/qwen')
files=file_manifest(path);model,tokenizer=load(path,files,'cuda')
schema=build_parameter_schema(model);snapshot=take_snapshot(model,schema);parent_hash=model_weights_sha256(model,schema)
workload=Path('docs/evidence/2026-10-26-vllm-impact/workload-chat-01.json')
selected=[r['tokenIds']for r in json.loads(workload.read_text())['models']['qwen']['rows'][:8]]
baseline=IntegerDecoderGraph(model,magnitude_bits=22,max_context=512,max_graph_bytes=6*1024**3)
engines={batch:SpeculativeGraph(model,magnitude_bits=22,max_context=512,max_graph_bytes=6*1024**3,
                               block=4 if batch==1 else 2)for batch in a.batches}
pad=tokenizer.pad_token_id or 0
report={'gpu':torch.cuda.get_device_name(),'modelFiles':files,'schemaHash':schema.hash,'parentSha256':parent_hash,
        'sourceSha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'workloadSha256':hashlib.sha256(workload.read_bytes()).hexdigest(),'cases':[],
        'limits':'Finite standalone Qwen pilot; EOS disabled, fixed128 outputs, parent-only proposal bank. '
                 'Parent proposal creation is measured separately and excluded from candidate warm timings. '
                 'No learning/managed/cross-GPU/native acceptance or near-vLLM claim.'}
run_base=bench.decoder_run(baseline,pad=pad,tokens=128)
start=time.perf_counter();parent=run_base(selected);torch.cuda.synchronize()
report['parentBankCreationSecondsIncludingWarmup']=time.perf_counter()-start
report['parentBankTokens']=parent
torch.cuda.reset_peak_memory_stats()
try:
    for state in a.states:
        restore_from_snapshot_(model,schema,snapshot)
        if state!='parent':perturb_model_(model,schema,7001,.001 if state=='plus'else-.001,engine=ENGINE_V2)
        weight_hash=model_weights_sha256(model,schema)
        for batch in a.batches:
            rows=selected[:batch];spec=engines[batch];proposer=SuffixProposer([[tokens]for tokens in parent[:batch]])
            class View:
                def __init__(self,provider):self.provider=provider
                def generate(self,*args,**kwargs):return spec.generate(*args,proposer=self.provider,**kwargs)
            runs={'baseline':run_base,'suffix':bench.decoder_run(View(proposer),pad=pad,tokens=128),
                  'empty':bench.decoder_run(View(None),pad=pad,tokens=128)}
            expected=run_base(rows)
            for name in ('suffix','empty'):assert runs[name](rows)==expected
            records=[]
            for name in ('baseline','suffix','empty','empty','suffix','baseline'):
                for _ in range(a.repeats):
                    begin=time.perf_counter();actual=runs[name](rows);torch.cuda.synchronize()
                    elapsed=time.perf_counter()-begin
                    assert actual==expected
                    records.append({'variant':name,'seconds':elapsed,'stats':copy.deepcopy(spec.stats)if name!='baseline'else None})
            raw={name:[r['seconds']for r in records if r['variant']==name]for name in runs}
            summary={name:{'medianSeconds':statistics.median(times),'tokensPerSecond':batch*128/statistics.median(times),
                           'speedRatio':statistics.median(raw['baseline'])/statistics.median(times)}for name,times in raw.items()}
            report['cases'].append({'state':state,'seed':None if state=='parent'else 7001,'sigma':0 if state=='parent'else(.001 if state=='plus'else-.001),
                                    'weightsSha256':weight_hash,'batch':batch,'block':spec.block,'promptTokenIds':rows,
                                    'tokens':expected,'records':records,'summary':summary})
            print(state,batch,json.dumps(summary),flush=True)
        restore_from_snapshot_(model,schema,snapshot)
        assert model_weights_sha256(model,schema)==parent_hash
finally:
    restore_from_snapshot_(model,schema,snapshot)
    report['restoreExact']=model_weights_sha256(model,schema)==parent_hash
report['peakAllocatedBytes']=torch.cuda.max_memory_allocated()
report['identities']={str(batch):e.kernel_identity()for batch,e in engines.items()}
report['status']='ok'
with a.out.open('x')as f:json.dump(report,f,indent=2);f.write('\n')
