import argparse,os,json,time,statistics,hashlib,importlib.util
from pathlib import Path
import torch
from heteroes.eval.strict_cuda import StrictCudaKernels
from prefill_tile import install
p=argparse.ArgumentParser();p.add_argument('--gpu',action='store_true');p.add_argument('--whole',action='store_true');p.add_argument('--qtile',type=int,default=8);p.add_argument('--headtile',type=int,default=1)
a=p.parse_args();assert a.gpu and os.environ.get('HETEROES_GPU_ACCEPTANCE')=='1'
data=json.loads(Path('docs/evidence/2026-10-26-vllm-impact/workload-chat-01.json').read_text())
rows=[r['tokenIds'] for r in data['models']['qwen']['rows'][:32]]
spans=[(len(r),len(r),0) for r in rows];n=sum(len(r) for r in rows)
if not a.whole:
    torch.manual_seed(123)
    q=torch.randn(14,n,64,device='cuda');k=torch.randn(2,n,64,device='cuda');v=torch.randn_like(k)
    kernels={'base':StrictCudaKernels('cuda')}
    for qt,ht in [(4,1),(8,1),(2,7),(4,3),(4,4),(2,8)]:
        label=f'{qt}x{ht}'
        kernels[label]=StrictCudaKernels('cuda');install(kernels[label],qt,ht)
    expected=None
    for name,ker in kernels.items():
        layout=ker.attention_layout(spans);flag=ker.new_error_flag()
        run=lambda:ker.attention_packed(q,k,v,layout,7,.125,error_flag=flag)
        out=run();torch.cuda.synchronize(); assert flag.item()==0
        if expected is None: expected=out
        else: assert torch.equal(out.view(torch.int32),expected.view(torch.int32))
        g=torch.cuda.CUDAGraph()
        with torch.cuda.graph(g): captured=run()
        times=[]
        for _ in range(7):
            s,e=torch.cuda.Event(enable_timing=True),torch.cuda.Event(enable_timing=True)
            s.record()
            for _ in range(20):g.replay()
            e.record();torch.cuda.synchronize();times.append(s.elapsed_time(e)*1000/20)
        print(name,statistics.median(times),'us', 'launches',getattr(ker,'tile_launches',0),flush=True)
else:
    from heteroes.eval.integer_decoder import IntegerDecoderGraph
    from heteroes.v3.model import load,file_manifest
    def module(name,path):
        spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
    bench=module('benchmark','runtime/scripts/benchmark_inference.py');probe=module('probe','runtime/scripts/probe_strict_backend.py')
    path=Path('/home/pc5070ti/projects/heteroes/.scratch/strict-integer-20261025/models/qwen')
    model,tok=load(path,file_manifest(path),'cuda')
    engines={name:IntegerDecoderGraph(model,magnitude_bits=22,max_context=512,max_graph_bytes=6*1024**3) for name in ['base','new']}
    install(engines['new'].kernels,a.qtile,a.headtile)
    short=[tok(t)['input_ids'] for t in probe.PROMPTS]
    for label,count,inputs in [('prefill',1,rows),('short32',32,[short[i%8] for i in range(32)]),('chat128',128,rows)]:
        runs={name:bench.decoder_run(eng,pad=tok.pad_token_id or 0,tokens=count) for name,eng in engines.items()}
        expected=runs['base'](inputs); assert runs['new'](inputs)==expected
        ts={n:[] for n in runs}
        for _ in range(5):
            for name in ['base','new','new','base']:
                torch.cuda.synchronize();t=time.perf_counter();out=runs[name](inputs);torch.cuda.synchronize();ts[name].append(time.perf_counter()-t)
                assert out==expected
        print(label,{name:round(32*count/statistics.median(t),1) for name,t in ts.items()},
              'ms',{name:round(1000*statistics.median(t),2) for name,t in ts.items()},hashlib.sha256(json.dumps(expected).encode()).hexdigest(),flush=True)
