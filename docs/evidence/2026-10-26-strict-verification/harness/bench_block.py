"""Fixed-prefix block scorer cost and exact serial logits: maximum-acceptance ceiling only."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import statistics

p=argparse.ArgumentParser();p.add_argument('--gpu',action='store_true');p.add_argument('--out',type=Path,required=True)
p.add_argument('--batches',type=int,nargs='+',choices=(1,8,32),default=[32])
a=p.parse_args()
if not a.gpu or os.environ.get('HETEROES_GPU_ACCEPTANCE')!='1' or a.out.exists():p.error('GPU opt-in/fresh output required')
import torch
from heteroes.eval.integer_decoder import IntegerDecoderGraph
from heteroes.v3.model import load,file_manifest
from block_verifier import BlockVerifier

path=Path('/home/pc5070ti/projects/heteroes/.scratch/strict-integer-20261025/models/qwen')
files=file_manifest(path);model,tokenizer=load(path,files,'cuda')
engines={str(block):IntegerDecoderGraph(model,magnitude_bits=22,max_context=512,max_graph_bytes=6*1024**3)
         for block in (1,2,4)}
serial=IntegerDecoderGraph(model,magnitude_bits=22,max_context=512,max_graph_bytes=6*1024**3)
rng=torch.Generator().manual_seed(1949)
report={'gpu':torch.cuda.get_device_name(),'modelFiles':files,'cases':[],
        'sourceSha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'limits':'Scorer-only GPU latency at fixed prefix. Every hypothetical position is verified, but no '
                 'proposal/acceptance/EOS/rollback loop or end-to-end speedup is measured. '
                 'Throughput is verified query positions/s, not emitted tokens/s.'}
torch.cuda.reset_peak_memory_stats()
for batch,context in ((b,c)for b in a.batches for c in (32,128)):
    prompts=[torch.randint(0,model.config.vocab_size,(1,context),generator=rng).cuda()for _ in range(batch)]
    guesses=torch.randint(0,model.config.vocab_size,(batch,4),generator=rng).cuda()
    expected=[]
    serial._generation_begin()
    try:
        _,cache=serial.forward_batch(prompts)
        for step in range(4):
            logits,cache=serial.forward_batch([guesses[i:i+1,step:step+1]for i in range(batch)],cache)
            expected.append(logits.detach().clone())
    finally:serial._generation_end()
    del cache,logits
    active={};raw={key:[]for key in engines}
    try:
        for key,engine in engines.items():
            verifier=BlockVerifier(engine,prompts,int(key));active[key]=verifier.__enter__()
            logits,chosen=verifier.run(guesses[:,:int(key)])
            expected_rows=torch.stack(expected[:int(key)],dim=1).reshape(-1,model.config.vocab_size)
            assert torch.equal(logits.view(torch.int32),expected_rows.view(torch.int32))
            assert torch.equal(chosen,expected_rows.argmax(-1).reshape(batch,int(key)))
        for key in ('1','2','4','4','2','1'):
            for _ in range(5):
                begin,end=torch.cuda.Event(enable_timing=True),torch.cuda.Event(enable_timing=True)
                begin.record();active[key].graph.replay();end.record();end.synchronize()
                raw[key].append(begin.elapsed_time(end))
                engines[key].kernels.raise_if_error(active[key].state.flag)
        summary={key:{'medianMs':statistics.median(times),
                      'costRelativeToOne':statistics.median(times)/statistics.median(raw['1']),
                      'verifiedQueryPositionsPerSecond':batch*int(key)*1000/statistics.median(times)}for key,times in raw.items()}
        report['cases'].append({'batch':batch,'prefixLength':context,'eventMs':raw,'summary':summary,
                                'allLogitBitsEqualSerial':True})
        print(batch,context,json.dumps(summary),flush=True)
    finally:
        for verifier in active.values():verifier.close()
report['peakAllocatedBytes']=torch.cuda.max_memory_allocated()
report['identities']={key:e.kernel_identity()for key,e in engines.items()}
report['status']='ok'
with a.out.open('x')as f:json.dump(report,f,indent=2);f.write('\n')
