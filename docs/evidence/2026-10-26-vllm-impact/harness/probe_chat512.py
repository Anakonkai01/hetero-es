"""Finite paired-GPU candidate scoring experiment, no updates or learning."""
import argparse
from functools import partial
import hashlib
import json
import os
from pathlib import Path
import time

p = argparse.ArgumentParser()
p.add_argument('--gpu', action='store_true')
p.add_argument('--model-path', type=Path, required=True)
p.add_argument('--workload', type=Path, required=True)
p.add_argument('--out', type=Path, required=True)
a = p.parse_args()
if not a.gpu or os.environ.get('HETEROES_GPU_ACCEPTANCE') != '1':
    p.error('GPU opt-in required')
if a.out.exists():
    p.error('Existing evidence')
if os.environ.get('VLLM_ENABLE_V1_MULTIPROCESSING') != '0':
    p.error('Single-process probe required')

import torch
import transformers
import vllm
from transformers import AutoConfig
from vllm import LLM, SamplingParams

from heteroes.v3.model import file_manifest
from probe_vllm_es import prepare, select_candidate

workload = json.loads(a.workload.read_text())
rows = workload['models'][a.model_path.name]['rows']
config = AutoConfig.from_pretrained(a.model_path, local_files_only=True, trust_remote_code=False)
report = {'status':'running', 'hardwareQualified':False, 'sourceSha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
          'workloadSha256':hashlib.sha256(a.workload.read_bytes()).hexdigest(), 'model':a.model_path.name,
          'modelFiles':file_manifest(a.model_path),'settings':{'batchSize':32,'maxNewTokens':512,'ignoreEos':False,
          'temperature':0,'seed':0,'sigma':1e-3,'candidateSeeds':[7001,7002,7003,7004],
          'batchInvariant':os.environ.get('VLLM_BATCH_INVARIANT','0'),'prefixCaching':False},
          'environment':{'torch':torch.__version__,'transformers':transformers.__version__,'vllm':vllm.__version__,
          'cuda':torch.version.cuda,'gpu':torch.cuda.get_device_name()},'cases':[],
          'limitations':'Finite scores and hypothetical coefficient comparisons; no ES update or learning.'}
engine = None
prepared = False
started = time.perf_counter()
try:
    engine = LLM(model=str(a.model_path), dtype='float16', max_model_len=1024,
                 gpu_memory_utilization=0.35, seed=0, enable_prefix_caching=False)

    def one(fn):
        outputs = engine.apply_model(fn)
        if len(outputs) != 1:
            raise ValueError('Expected one model owner')
        return outputs[0]

    report['preparation'] = one(partial(prepare,config=config))
    prepared = True
    params = SamplingParams(temperature=0.0,max_tokens=512,ignore_eos=False,repetition_penalty=1.0)
    descriptors = [('parent',7001,0)] + [(f'{seed}{sign:+d}',seed,sign) for seed in (7001,7002,7003,7004) for sign in (1,-1)] + [('restored',7001,0)]
    for label,seed,sign in descriptors:
        publication = one(partial(select_candidate,state='plus' if sign==1 else 'minus' if sign==-1 else 'restored',seed=seed,sigma=1e-3))
        if not engine.reset_prefix_cache():
            raise ValueError('Cache reset failed')
        case = {'label':label,'candidateSeed':seed if sign else None,'sign':sign,**publication,'outputs':[]}
        report['cases'].append(case)
        start = time.perf_counter()
        for offset in range(0,len(rows),32):
            subset = rows[offset:offset+32]
            outputs = engine.generate([{'prompt_token_ids':r['tokenIds']} for r in subset],params,use_tqdm=False)
            if len(outputs)!=len(subset):
                raise ValueError('Generation count mismatch')
            for row,result in zip(subset,outputs,strict=True):
                completion = result.outputs[0]
                case['outputs'].append({'id':row['id'],'tokens':list(completion.token_ids),'text':completion.text,
                                        'finishReason':completion.finish_reason,'stopReason':completion.stop_reason})
        torch.cuda.synchronize()
        case['generationSeconds'] = time.perf_counter()-start
        print(json.dumps({'label':label,'rows':len(case['outputs']),'generationSeconds':case['generationSeconds']}),flush=True)
    report['status']='ok'
except Exception as error:
    report.update(status='error',errorType=type(error).__name__,error=str(error)[:2000])
finally:
    if prepared:
        try:
            report['finalRestore']=engine.apply_model(partial(select_candidate,state='restored',seed=7001,sigma=1e-3))[0]
            if not report['finalRestore']['parentRestored']:
                raise ValueError('Final restore mismatch')
        except Exception as error:
            report.update(status='error',restoreError=str(error)[:2000])
report['wallSeconds']=time.perf_counter()-started
with a.out.open('x') as f:
    json.dump(report,f,indent=2,allow_nan=False)
    f.write('\n')
print(json.dumps({'status':report['status'],'out':str(a.out),'wallSeconds':report['wallSeconds']}),flush=True)
raise SystemExit(int(report['status']!='ok'))
