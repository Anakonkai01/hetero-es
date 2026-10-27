"""Offline exact-integer pruning density, not a faster head implementation or throughput result."""
import argparse,hashlib,importlib.util,json,os,statistics
from pathlib import Path
import torch
from heteroes.eval.integer_decoder import IntegerDecoderGraph
from heteroes.v3.model import load,file_manifest

p=argparse.ArgumentParser();p.add_argument('--gpu',action='store_true');p.add_argument('--out',type=Path,required=True)
a=p.parse_args();assert a.gpu and os.environ.get('HETEROES_GPU_ACCEPTANCE')=='1' and not a.out.exists()
def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
bench=module('benchmark','runtime/scripts/benchmark_inference.py');probe=module('probe','runtime/scripts/probe_strict_backend.py')
class CaptureHidden(IntegerDecoderGraph):
    def _decode_output(self,hidden,epsilon,state):
        self.sample_hidden=hidden.clone()
        return super()._decode_output(hidden,epsilon,state)

@torch.inference_mode()
def run():
    path=Path('/home/pc5070ti/projects/heteroes/.scratch/strict-integer-20261025/models/qwen')
    files=file_manifest(path);model,tok=load(path,files,'cuda')
    engine=CaptureHidden(model,magnitude_bits=22,max_context=512,max_graph_bytes=6*1024**3)
    short=[tok(t)['input_ids'] for t in probe.PROMPTS]
    chat=json.loads(Path('docs/evidence/2026-10-26-vllm-impact/workload-chat-01.json').read_text())['models']['qwen']['rows']
    report={'status':'running','runtimeCommit':'0eb86cb9','gpu':torch.cuda.get_device_name(),'modelFiles':files,
            'sourceSha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'cases':[],
            'limits':__doc__+' FP64 GEMM is used only as an exact integer dot evaluator (products/sums below 2^53). It is not a runtime proposal.'}
    k=engine.kernels;head=engine._bounded_head;weight=model.lm_head.weight;v,width=weight.shape
    assert v%32==0
    for label,n,rows in [('short2',2,[short[i%8] for i in range(32)]),('short8',8,[short[i%8] for i in range(32)]),
                         ('short32',32,[short[i%8] for i in range(32)]),('chat32',32,[r['tokenIds'] for r in chat[:32]]),
                         ('chat128',128,[r['tokenIds'] for r in chat[:32]])]:
        output=bench.decoder_run(engine,pad=tok.pad_token_id or 0,tokens=n)(rows)
        hidden=engine.sample_hidden
        k._begin_request(engine._projection_weights());head.prepare(weight)
        flag=k.new_error_flag();prepared=k.rms_norm_quantized(hidden,model.model.norm.weight,float(model.config.rms_norm_eps),error_flag=flag)
        planes,ex=prepared
        digits=planes.view(torch.int8).reshape(3,32,width).to(torch.int64)
        qa=digits[0]+256*digits[1]+65536*digits[2]
        qsum=qa.sum(1,keepdim=True);qabs=qa.abs().sum(1,keepdim=True)
        ew=k._weight_exponents(weight,flag);shifts=(15-ew).long()
        assert shifts.min()>=0 and shifts.max()<=62
        divisor=(torch.ones_like(shifts)<<shifts)[None,:]
        old_hi,old_lo=head.bounds(prepared,weight)
        winner=torch.tensor([r[-1] for r in output],device='cuda')//32
        item={'case':label,'outputTokens':n,'winningTiles':winner.cpu().tolist(),'variants':[]}
        for shift in (15,16,17,18,19):
            coarse=(head.buffer.to(torch.int16)>>(shift-15)).double()
            product=qa.double()@coarse.T
            assert product.abs().max()<2.**53
            center=(product.to(torch.int64)<<shift)+(qsum<<(shift-1));radius=qabs<<(shift-1)
            upper=(center+radius+divisor-1)>>shifts[None,:]
            lower=(center-radius)>>shifts[None,:]
            upper=upper.reshape(32,v//32,32).amax(2);lower=lower.reshape(32,v//32,32).amax(2)
            hi=torch.ldexp(upper.double(),(ex-27)[:,None]).float()
            lo=torch.ldexp(lower.double(),(ex-27)[:,None]).float()
            assert torch.isfinite(hi).all() and torch.isfinite(lo).all()
            if shift==15:
                assert torch.equal(hi.view(torch.int32),old_hi.view(torch.int32))
                assert torch.equal(lo.view(torch.int32),old_lo.view(torch.int32))
            keep=hi>=lo.amax(1,keepdim=True);counts=keep.sum(1)
            assert keep.gather(1,winner[:,None]).all()
            entry={'signedWeightBits':23-shift,'shift':shift,'survivingTileCounts':counts.cpu().tolist(),
                   'median':float(counts.double().median()),'mean':float(counts.double().mean()),'max':int(counts.max()),'allWinningTilesKept':True}
            item['variants'].append(entry);print(label,entry['signedWeightBits'],entry['median'],round(entry['mean'],2),entry['max'],flush=True)
            del coarse,product,center,upper,lower
        k.raise_if_error(flag);head.clear();k._end_request();report['cases'].append(item)
    report['status']='ok'
    with a.out.open('x') as f:json.dump(report,f,indent=2);f.write('\n')
run()
