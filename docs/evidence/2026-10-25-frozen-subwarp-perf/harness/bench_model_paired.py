"""One primary pinned model, two bounded graph workspaces; compare the exact warp and output schedules."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import statistics
import time

parser=argparse.ArgumentParser()
parser.add_argument('--gpu',action='store_true')
parser.add_argument('--model-path',type=Path,required=True)
parser.add_argument('--bundle',type=Path,required=True)
parser.add_argument('--out',type=Path,required=True)
parser.add_argument('--benchmark',type=Path,required=True)
parser.add_argument('--states',nargs='+',default=['zero','probe','plus','minus'])
parser.add_argument('--repeats',type=int,default=5)
args=parser.parse_args()
if args.out.exists():parser.error('Existing evidence')
if not args.gpu or os.environ.get('HETEROES_GPU_ACCEPTANCE')!='1':parser.error('GPU opt-in')
import torch
import transformers
from heteroes.eval.frozen_int8_decoder import FrozenInt8DecoderGraph
from heteroes.eval.phase_trace import storage_inventory
from heteroes.eval.workload import extract_integer
from heteroes.model.frozen_int8 import freeze_projections,freeze_tied_head,load_frozen_adapter_
from heteroes.model.weights_io import sha256_of_file
from heteroes.v3.model import file_manifest,load
from heteroes.model.lora import trainable_schema
from heteroes.eval.candidate import model_weights_sha256

bundle=json.loads((args.bundle/'manifest.json').read_text())
identity=dict(bundle);declared=identity.pop('bundleSha256')
assert hashlib.sha256(json.dumps(identity,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode()).hexdigest()==declared
for name,digest in bundle['files'].items():assert sha256_of_file(args.bundle/name)==digest,name
files=file_manifest(args.model_path)
assert files==bundle['parentFiles'],'parent model files differ'
spec=importlib.util.spec_from_file_location('benchmark',args.benchmark)
bench=importlib.util.module_from_spec(spec);spec.loader.exec_module(bench)
probe_spec=importlib.util.spec_from_file_location('probe',args.benchmark.with_name('probe_strict_backend.py'))
probe=importlib.util.module_from_spec(probe_spec);probe_spec.loader.exec_module(probe)
model,tokenizer=load(args.model_path,files,'cpu')
digests=freeze_projections(model,rank=bundle['rank'],alpha=bundle['alpha'],seed=bundle['adapterSeed'],
    artifact_directory=args.bundle/'projections',expected_sha256=bundle['frozenArtifacts'])
assert digests==bundle['frozenArtifacts']
if bundle['headArtifact']:
    assert freeze_tied_head(model,artifact_path=args.bundle/'head.fint8',expected_sha256=bundle['headArtifact'])==bundle['headArtifact']
model.cuda()
schema=trainable_schema(model)
assert schema.hash==bundle['schemaHash']
prompts=[tokenizer(text)['input_ids'] for text in probe.PROMPTS]
engines={};runs={}
for execution in ('warp','output'):
    engine=FrozenInt8DecoderGraph(model,max_context=512,max_graph_bytes=4*1024**3,max_partial_bytes=64*1024**2)
    original=engine.kernels.lora_finish
    def finish(*items,_method=original,_execution=execution,**options):
        return _method(*items,**{**options,'execution':_execution,'row_tile':8})
    engine.kernels.lora_finish=finish
    engines[execution]=engine
    runs[execution]=bench.decoder_run(engine,pad=tokenizer.pad_token_id or 0,tokens=32)
assert engines['warp'].model is engines['output'].model
report={'bundleSha256':declared,'modelFiles':files,'promptTokenIds':prompts,'headVariant':bundle['headVariant'],
        'gpu':torch.cuda.get_device_name(0),'torch':torch.__version__,'cuda':torch.version.cuda,
        'transformers':transformers.__version__,'cases':[],'comparisons':[],'generated':[],
        'onePrimaryWeightSet':True,'workspaces':'two bounded graph/KV workspaces, shared primary tensors',
        'sourceSha256':hashlib.sha256(Path(__import__('heteroes.eval.strict_cuda',fromlist=['']).__file__).read_bytes()).hexdigest()}
expected=(4,8,32,72,None,270,None,None)
for state in args.states:
    adapter=bundle['adapters'][state]
    load_frozen_adapter_(model,args.bundle/adapter['path'],adapter['sha256'])
    assert model_weights_sha256(model,schema)==adapter['sha256']
    for batch in (1,8,32):
        selected=[prompts[i%8] for i in range(batch)]
        actual={execution:run(selected) for execution,run in runs.items()}
        assert actual['warp']==actual['output'],(state,batch,'token mismatch')
        texts=tokenizer.batch_decode(actual['output'],skip_special_tokens=True)
        rewards=[None if expected[i%8] is None else int(extract_integer(text)==expected[i%8]) for i,text in enumerate(texts)]
        report['generated'].append({'state':state,'batch':batch,'tokens':actual['output'],'texts':texts,'rewards':rewards,
            'fullStreamSha256':hashlib.sha256(json.dumps(actual['output'],separators=(',',':')).encode()).hexdigest()})
        if state in ('zero','probe'):
            records=[]
            for execution in ('warp','output','output','warp'):
                result=bench.measure(runs[execution],selected,32,args.repeats,torch.cuda.synchronize)
                assert result['repeatTokensEqual'] and result['tokens']==actual[execution]
                records.append({'execution':execution,**result})
            warp=[d for r in records if r['execution']=='warp' for d in r['seconds']]
            output=[d for r in records if r['execution']=='output' for d in r['seconds']]
            ratio=statistics.median(warp)/statistics.median(output)
            report['cases'].append({'state':state,'batch':batch,'records':records})
            report['comparisons'].append({'state':state,'batch':batch,'warpTokensPerSecond':32*batch/statistics.median(warp),
                'outputTokensPerSecond':32*batch/statistics.median(output),'ratio':ratio})
            print(state,batch,report['comparisons'][-1],flush=True)
    # Prefill logits are a stronger finite check than the required token/text/reward comparison.
    ids=torch.tensor([prompts[0]],device='cuda')
    logits=[]
    for engine in engines.values():
        value,_=engine.forward_tokens(ids)
        logits.append(value.cpu().contiguous())
    assert torch.equal(logits[0].view(torch.int32),logits[1].view(torch.int32)),(state,'logit mismatch')
    report.setdefault('prefillLogits',[]).append({'state':state,'sha256':hashlib.sha256(logits[0].numpy().tobytes()).hexdigest()})
    assert model_weights_sha256(model,schema)==adapter['sha256']
load_frozen_adapter_(model,args.bundle/bundle['adapters']['probe']['path'],bundle['adapters']['probe']['sha256'])
assert model_weights_sha256(model,schema)==bundle['adapters']['probe']['sha256']
for execution,run in runs.items():
    expected_probe=next(r['tokens'] for r in report['generated'] if r['state']=='probe' and r['batch']==8)
    assert run(prompts)==expected_probe,(execution,'restore tokens')
for name,digest in bundle['files'].items():assert sha256_of_file(args.bundle/name)==digest,name
report['storageInventory']=storage_inventory({'warp':model,'output':model})
report['kernelIdentity']={name:engine.kernel_identity() for name,engine in engines.items()}
report['peakAllocatedBytes']=torch.cuda.max_memory_allocated()
report['peakReservedBytes']=torch.cuda.max_memory_reserved()
with args.out.open('x') as f:json.dump(report,f,indent=2);f.write('\n')
print('DONE',args.out,flush=True)
