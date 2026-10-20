"""Read-only exact candidate probe, explicitly authorized GPU execution only."""
import argparse,json,os,time
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--gpu',action='store_true',required=True);p.add_argument('--model',required=True);p.add_argument('--inputs',required=True);p.add_argument('--out',required=True);p.add_argument('--modes',default='sdpa,eager,math,float64')
a=p.parse_args();assert os.environ.get('HETEROES_GPU_ACCEPTANCE')=='1';root=Path(a.inputs)
import torch
from heteroes.es.update import apply_coefficients_
from heteroes.eval.candidate import model_weights_sha256,tensors_sha256
from heteroes.executor import CandidateExecutor
from heteroes.generation_record import GenerationRecord
from heteroes.manifest import CandidateDescriptor
from heteroes.runtime_info import environment_info
from heteroes.v3.data import open_dataset
from heteroes.v3.model import load,trainable_schema
from heteroes.v3.run import RecipeV3Run
from heteroes.worker_api import completions_sha256
recipe=json.loads((root/'recipe.json').read_text());plan=json.loads((root/'plan.json').read_text());run=RecipeV3Run(recipe,plan)
data=open_dataset(root/'dataset.json');candidate=json.loads((root/'candidate.json').read_text());desc=CandidateDescriptor(**candidate['descriptor'])
model,tok=load(a.model,recipe['model']['files'],'cuda');schema=trainable_schema(model,recipe['weightSpace']);assert schema.hash==recipe['schemaHash']
children=[]
for u in json.loads((root/'updates.json').read_text()):
 record=GenerationRecord.from_dict(u['record']);assert model_weights_sha256(model,schema)==record.parent_weights_sha256
 seeds,coeff=record.update_inputs();apply_coefficients_(model,schema,seeds,coeff,record.alpha,run.chunk_elements)
 child=model_weights_sha256(model,schema);assert child==u['childSha256'];children.append(child);print(json.dumps({'reconstructedGeneration':u['generation'],'child':child}),flush=True)
assert children[-1]==desc.parent_weights_sha256
from heteroes.model.weights_io import write_weights
cache=root/'parent-fp16.bin'
if not cache.exists():
 assert write_weights(model,schema,cache)==desc.parent_weights_sha256
executor=CandidateExecutor(model,tok,schema,run,dataset=data,return_completions=True);executor.set_generation(desc.generation,run.context(data,desc.generation))
captures=[];generate=executor._eval.model.generate

def trace(*args,**kwargs):
 capture={'inputIds':kwargs['input_ids'].cpu().tolist(),'attentionMask':kwargs['attention_mask'].cpu().tolist(),'perturbedFp16Sha256':model_weights_sha256(model,schema),'evaluationFp32Sha256':tensors_sha256(list(executor._eval.model.parameters()))}
 torch.cuda.synchronize();started=time.perf_counter()
 reply=generate(*args,**kwargs,return_dict_in_generate=True,output_scores=True)
 torch.cuda.synchronize();capture['generateSeconds']=time.perf_counter()-started
 ids=reply.sequences;capture['newTokenIds']=ids[:,kwargs['input_ids'].shape[1]:].cpu().tolist()
 capture['topTwo']=[{'indices':torch.topk(v,2,dim=-1).indices.cpu().tolist(),'values':torch.topk(v,2,dim=-1).values.cpu().tolist()} for v in reply.scores]
 captures.append(capture);return ids
executor._eval.model.generate=trace
results=[]
from torch.utils._python_dispatch import TorchDispatchMode
from functools import wraps
class FullPrecision(TorchDispatchMode):
 def __torch_dispatch__(self,func,types,args=(),kwargs=None):
  kwargs=kwargs or {}
  if func==torch.ops.aten._to_copy.default and kwargs.get('dtype')==torch.float32:
   kwargs={**kwargs,'dtype':torch.float64}
  return func(*args,**kwargs)
from contextlib import nullcontext
from torch.nn.attention import sdpa_kernel,SDPBackend
original_shadow=executor._eval.model
original_forward=original_shadow.forward
for mode in a.modes.split(','):
 executor._eval._shadow=original_shadow
 original_shadow.set_attn_implementation('eager' if mode=='eager' else 'sdpa')
 if mode in ('float64','precise64'):
  original_shadow.double()
 if mode=='precise64':
  @wraps(original_forward)
  def precise_forward(*args,**kwargs):
   with FullPrecision():return original_forward(*args,**kwargs)
  original_shadow.forward=precise_forward
 for i in range(1):
  with (sdpa_kernel(SDPBackend.MATH) if mode=='math' else nullcontext()):
   texts=list(executor(desc))
  sha=completions_sha256(texts);restored=model_weights_sha256(model,schema);assert restored==desc.parent_weights_sha256
  results.append({'mode':mode,'texts':texts,'sha256':sha,'equalsCommitted':sha==candidate['committedCompletionsSha256'],'restoredParentSha256':restored,'capture':captures[-1]})
  print(json.dumps({'mode':mode,'sha256':sha,'equalsCommitted':results[-1]['equalsCommitted']}),flush=True)
settings={'matmulPrecision':torch.get_float32_matmul_precision(),'matmulAllowTf32':torch.backends.cuda.matmul.allow_tf32,'cudnnAllowTf32':torch.backends.cudnn.allow_tf32,'attentionImplementation':getattr(model.config,'_attn_implementation',None),'deterministicAlgorithms':torch.are_deterministic_algorithms_enabled()}
out={'environment':environment_info('cuda'),'settings':settings,'descriptor':desc.to_dict(),'context':run.context(data,desc.generation),'children':children,'results':results}
with open(a.out,'x') as f:json.dump(out,f,indent=1);f.write('\n')
