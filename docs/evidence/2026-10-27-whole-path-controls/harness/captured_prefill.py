"""Shape-captured prefill probe for the current deferred-flag forward API; numerical operators are unchanged."""
import hashlib
import inspect
from itertools import chain
from pathlib import Path
import textwrap
import torch
from heteroes.canonical import canonical_json_hash
from heteroes.eval import reference_ops as ops
from heteroes.eval.integer_decoder import IntegerDecoderGraph
from heteroes.eval.reference_ops import ReferenceArithmeticError
from heteroes.eval.strict_decoder_packed import StrictDecoderPacked,PackedCaches

CORE=textwrap.dedent(inspect.getsource(StrictDecoderPacked.forward_batch))
changes={
 'def forward_batch(':'def _prefill_core(',
 '    ids = torch.cat(rows, dim=1)[0]':'    ids = self._prefill_ids',
 '    layout = kernels.attention_layout(spans)':'    layout = self._prefill_layout',
 '    positions = torch.tensor(\n        [p + i for length, p in zip(lengths, pasts) for i in range(length)], dtype=torch.long, device=self.device\n    )':'    positions = self._prefill_positions',
 '    flag = kernels.new_error_flag() if error_flag is None else error_flag':'    flag = self._prefill_flag\n    flag.zero_()',
 '    selected = hidden[torch.tensor(last, dtype=torch.long, device=self.device)]':'    selected = hidden[self._prefill_last]',
}
for old,new in changes.items():
 assert CORE.count(old)==1,old
 CORE=CORE.replace(old,new)
scope={'torch':torch,'ops':ops,'ReferenceArithmeticError':ReferenceArithmeticError,'PackedCaches':PackedCaches}
exec(CORE,scope)

class PrefillIntegerGraph(IntegerDecoderGraph):
 _prefill_core=scope['_prefill_core']
 def __init__(self,*args,**kwargs):
  super().__init__(*args,**kwargs)
  self._drop_prefill();self._prefill_active=False;self.prefill_capture_count=0
  self.identity={**self.identity,'prefillExecution':'shape_capture_deferred_flags_probe','prefillCoreSha256':hashlib.sha256(CORE.encode()).hexdigest(),'prefillSourceSha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
  self.fingerprint=canonical_json_hash(self.identity)
 def _drop_prefill(self):
  self._prefill_graph=self._prefill_key=self._prefill_output=None
  self._prefill_ids=self._prefill_flag=self._prefill_layout=self._prefill_positions=self._prefill_last=None
  self._prefill_rows=self._prefill_retained=()
 def _request_workspace_bytes(self,capacity=1):
  c=self.config;p=capacity*self.max_context;q=c.num_attention_heads*self.head_dim;kv=c.num_key_value_heads*self.head_dim
  extra=4*p*(16*c.hidden_size+8*q+8*kv+4*c.intermediate_size)+2*c.num_hidden_layers*p*kv*4+24*p+capacity*c.vocab_size*4
  return super()._request_workspace_bytes(capacity)+extra
 def _release_graph(self):
  super()._release_graph();self._drop_prefill()
 def _generation_begin(self):
  super()._generation_begin();self._prefill_active=self._session is not None
 def _generation_end(self):
  try:super()._generation_end()
  finally:
   if self._prefill_retained:torch._foreach_zero_(list(self._prefill_retained))
   torch.cuda.current_stream(self.device).synchronize();self._prefill_active=False
 def prefill_request_buffers(self):return self._prefill_retained
 def buffers(self,*args,**kwargs):return chain(super().buffers(*args,**kwargs),self.prefill_request_buffers())
 @torch.inference_mode()
 def forward_batch(self,rows,caches=None,*,error_flag=None,_validated=False):
  if not self._prefill_active or caches is not None:return super().forward_batch(rows,caches,error_flag=error_flag,_validated=_validated)
  lengths,_=self._batch_layout(rows,[None]*len(rows));ids=torch.cat(rows,dim=1)[0]
  if not _validated and bool(((ids<0)|(ids>=self.config.vocab_size)).any()):raise ReferenceArithmeticError('Packed input token outside vocabulary')
  binding=tuple((id(p),p.data_ptr(),tuple(p.shape),tuple(p.stride()),p.dtype,p.device) for p in self.model.parameters())
  metadata=tuple(t.data_ptr() for t in self.kernels.weight_metadata_buffers())
  key=(tuple(lengths),binding,metadata,torch.cuda.current_stream(self.device).cuda_stream)
  if self._prefill_graph is None or self._prefill_key!=key:
   self._drop_prefill();self._prefill_ids=ids.clone();offset=0;static=[];last=[]
   for length in lengths:
    static.append(self._prefill_ids[offset:offset+length][None]);offset+=length;last.append(offset-1)
   self._prefill_rows=tuple(static)
   self._prefill_layout=self.kernels.attention_layout([(length,length,0) for length in lengths])
   self._prefill_positions=torch.tensor([i for length in lengths for i in range(length)],dtype=torch.long,device=self.device)
   self._prefill_last=torch.tensor(last,dtype=torch.long,device=self.device);self._prefill_flag=self.kernels.new_error_flag()
   warm=self._prefill_core(self._prefill_rows,error_flag=self._prefill_flag,_validated=True);self.kernels.raise_if_error(self._prefill_flag);del warm
   graph=torch.cuda.CUDAGraph()
   with torch.cuda.graph(graph):output=self._prefill_core(self._prefill_rows,error_flag=self._prefill_flag,_validated=True)
   self._prefill_graph,self._prefill_output,self._prefill_key=graph,output,key
   self._prefill_retained=(self._prefill_ids,self._prefill_flag,output[0],*(t for pair in output[1].slabs for t in pair));self.prefill_capture_count+=1
  else:self._prefill_ids.copy_(ids)
  self._prefill_graph.replay()
  if error_flag is None:self.kernels.raise_if_error(self._prefill_flag)
  else:error_flag.bitwise_or_(self._prefill_flag)
  return self._prefill_output
