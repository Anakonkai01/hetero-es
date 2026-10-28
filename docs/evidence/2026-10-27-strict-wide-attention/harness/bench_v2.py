"""Actual short-prompt length distribution, synthetic tensors, matched graph-replayed attention only."""
import argparse,hashlib,importlib.util,json,os,statistics
from pathlib import Path
import torch
from transformers import AutoTokenizer
from heteroes.eval import strict_cuda as sc
from wide_attention_v2 import WideAttention
p=argparse.ArgumentParser();p.add_argument('--gpu',action='store_true');p.add_argument('--out',type=Path,required=True);a=p.parse_args();assert a.gpu and os.environ.get('HETEROES_GPU_ACCEPTANCE')=='1' and not a.out.exists()
new=WideAttention();old=sc.StrictCudaKernels('cuda');flag=old.new_error_flag();gen=torch.Generator(device='cuda').manual_seed(71)
spec=importlib.util.spec_from_file_location('prompts','runtime/scripts/probe_strict_backend.py');mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
tok=AutoTokenizer.from_pretrained('/home/pc5070ti/projects/heteroes/.scratch/strict-integer-20261025/models/qwen',local_files_only=True,trust_remote_code=False)
lens=[len(tok(t)['input_ids']) for t in mod.PROMPTS]
report={'status':'running','gpu':torch.cuda.get_device_name(),'sourceSha256':hashlib.sha256(Path(__file__).with_name('wide_attention_v2.py').read_bytes()).hexdigest(),'promptLengths':lens,'cases':[],'limits':__doc__+' No whole-generation gain or multi-platform qualification.'}
def timing(call):
    call();torch.cuda.synchronize();graph=torch.cuda.CUDAGraph()
    with torch.cuda.graph(graph):
      for _ in range(8):call()
    times=[]
    for _ in range(11):
      start,end=torch.cuda.Event(enable_timing=True),torch.cuda.Event(enable_timing=True)
      start.record();graph.replay();end.record();end.synchronize();times.append(start.elapsed_time(end)*1000/8)
    return times
for rows,step in ((32,1),(32,16),(32,31),(32,128-max(lens)),(8,16),(2,16)):
    lengths=[lens[i%8]+step for i in range(rows)];assert max(lengths)<=128
    q=torch.randn(14,rows,64,device='cuda',generator=gen);key=torch.randn(2,rows*512,64,device='cuda',generator=gen);value=torch.randn_like(key)
    layout=sc._PackedAttentionLayout(torch.tensor([(i*512,n,n-1) for i,n in enumerate(lengths)],dtype=torch.int32,device='cuda'),rows,rows*512,max(lengths))
    def base():return old.attention_packed(q,key,value,layout,7,.125,error_flag=flag)
    def wide():return new.run(q,key,value,layout,flag)
    expected=base();assert torch.equal(wide().view(torch.int32),expected.view(torch.int32))
    item={'rows':rows,'step':step,'lengths':lengths,'variants':[]}
    for name,call in [('base',base),('wide',wide),('base-repeat',base)]:
      times=timing(call);item['variants'].append({'name':name,'microseconds':times,'median':statistics.median(times)})
      print(rows,step,name,round(statistics.median(times),3),'us',flush=True)
    assert flag.item()==0
    report['cases'].append(item)
attr=old._driver.CUfunction_attribute
report['resources']={}
for label,owner,fn,threads in [('old',old,old._ops('strict_attention_gqa'),448),('wide',new.owner,new.fn,896)]:
 report['resources'][label]={'registers':sc._check(owner._driver.cuFuncGetAttribute(attr.CU_FUNC_ATTRIBUTE_NUM_REGS,fn)),'localBytes':sc._check(owner._driver.cuFuncGetAttribute(attr.CU_FUNC_ATTRIBUTE_LOCAL_SIZE_BYTES,fn)),'threads':threads}
report['builds']=new.owner._builds;report['status']='ok'
with a.out.open('x') as f:json.dump(report,f,indent=2);f.write('\n')
