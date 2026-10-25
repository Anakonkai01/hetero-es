"""Selected full-weight B22 prefetch2 versus prior architecture-specific reads, same primary FP16 model, ABBA host wall timings."""
import argparse,hashlib,importlib.util,json,os,statistics
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--gpu',action='store_true');p.add_argument('--model',required=True)
p.add_argument('--models-root',type=Path,required=True);p.add_argument('--benchmark',type=Path,required=True)
p.add_argument('--out',type=Path,required=True);a=p.parse_args()
if a.out.exists():p.error('Existing evidence')
if not a.gpu or os.environ.get('HETEROES_GPU_ACCEPTANCE')!='1':p.error('GPU opt-in')
import torch
from heteroes.eval.integer_decoder import IntegerDecoderGraph
from heteroes.v3.model import file_manifest,load
spec=importlib.util.spec_from_file_location('benchmark',a.benchmark)
bench=importlib.util.module_from_spec(spec);spec.loader.exec_module(bench)
spec=importlib.util.spec_from_file_location('probe',a.benchmark.with_name('probe_strict_backend.py'))
probe=importlib.util.module_from_spec(spec);spec.loader.exec_module(probe)
files=file_manifest(a.models_root/a.model)
model,tokenizer=load(a.models_root/a.model,files,'cuda')
prompts=[tokenizer(text)['input_ids'] for text in probe.PROMPTS]
engines={};runs={}
old_mode='paired' if torch.cuda.get_device_capability()==(12,0) else 'scalar'
for label in ('baseline','prefetch'):
    engine=IntegerDecoderGraph(model,magnitude_bits=22,max_context=512,max_graph_bytes=4*1024**3,weight_load=old_mode if label=='baseline' else 'auto')
    engines[label]=engine
    runs[label]=bench.decoder_run(engine,pad=tokenizer.pad_token_id or 0,tokens=32)
report={'gpu':torch.cuda.get_device_name(0),'modelFiles':files,'promptTokenIds':prompts,'cases':[],'comparisons':[]}
for batch in (1,8,32):
    selected=[prompts[i%8] for i in range(batch)]
    actual={name:run(selected) for name,run in runs.items()}
    assert actual['baseline']==actual['prefetch'],batch
    records=[]
    for name in ('baseline','prefetch','prefetch','baseline'):
        result=bench.measure(runs[name],selected,32,5,torch.cuda.synchronize)
        assert result['repeatTokensEqual'] and result['tokens']==actual[name]
        records.append({'variant':name,**result})
    raw={name:[t for r in records if r['variant']==name for t in r['seconds']] for name in engines}
    before=32*batch/statistics.median(raw['baseline']);after=32*batch/statistics.median(raw['prefetch'])
    report['cases'].append({'batch':batch,'records':records})
    report['comparisons'].append({'batch':batch,'before':before,'after':after,'ratio':after/before})
    print(a.model,report['comparisons'][-1],flush=True)
report['identities']={name:engine.kernel_identity() for name,engine in engines.items()}
assert report['identities']['prefetch']['weightLoadEffective']=='prefetch2'
assert any('-prefetch2' in name for name in report['identities']['prefetch']['builds'])
assert not any('-prefetch2' in name for name in report['identities']['baseline']['builds'])
with a.out.open('x') as f:json.dump(report,f,indent=2);f.write('\n')
print('DONE',a.out,flush=True)
