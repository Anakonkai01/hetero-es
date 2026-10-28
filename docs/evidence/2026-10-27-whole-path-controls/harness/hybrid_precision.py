"""Unselected mixed projection contract: MLP B14, attention/head B22, original strict FP32 nonlinearities.

One shared FP16 model; precision follows canonical module roles, independent of batch/cache/phase. Historical
B22/B14 implementations and defaults are unchanged. This probe still needs numerical/resource/platform gates.
"""
import hashlib
from itertools import chain
from pathlib import Path
from heteroes.canonical import canonical_json_hash
from heteroes.eval import integer_reference as reference
from heteroes.eval.integer_cuda import IntegerCudaKernels
from heteroes.eval.integer_decoder import IntegerDecoderGraph,IntegerDecoderReference
from heteroes.eval.reference_ops import ReferenceArithmeticError
from heteroes.eval.strict_decoder_graph import StrictDecoderGraph

POLICY={'attention':22,'mlp':14,'lm_head':22}

def mlp_modules(model):
 return tuple(getattr(layer.mlp,name) for layer in model.model.layers for name in ('gate_proj','up_proj','down_proj'))
def attention_modules(model):
 return tuple(getattr(layer.self_attn,name) for layer in model.model.layers for name in ('q_proj','k_proj','v_proj','o_proj'))+(model.lm_head,)
def identity(base,backend):
 return {**base,'backend':backend,'projectionPrecisions':POLICY,'mixedSourceSha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'hardwareQualified':False}

class MixedDecoderReference(IntegerDecoderReference):
 def __init__(self,model,**kwargs):
  super().__init__(model,magnitude_bits=22,**kwargs)
  self.identity=identity(self.identity,'decoder_mlp14_attention22_reference_v1_probe');self.fingerprint=canonical_json_hash(self.identity)
 def _linear(self,value,module):
  bits=14 if any(module is m for m in mlp_modules(self.model)) else 22
  return reference.linear(value,module.weight,getattr(module,'bias',None),magnitude_bits=bits)

class MixedDecoderGraph(IntegerDecoderGraph):
 def __init__(self,model,**kwargs):
  super().__init__(model,magnitude_bits=22,**kwargs)
  self._mlp_kernels=IntegerCudaKernels(self.device,magnitude_bits=14,max_partial_bytes=self.kernels.max_partial_bytes,weight_load=self.kernels.weight_load,mma_schedule=self.kernels.mma_schedule)
  self._refresh_roles()
  self.identity=identity(self.identity,'decoder_mlp14_attention22_cuda_graph_v1_probe')
  self.identity['mlpKernels']=self._mlp_kernels.identity();self.fingerprint=canonical_json_hash(self.identity)
 def _refresh_roles(self):
  self._mlp_ids={id(m) for m in mlp_modules(self.model)}
  if {id(m.weight) for m in mlp_modules(self.model)} & {id(m.weight) for m in attention_modules(self.model)}:
   raise ReferenceArithmeticError('Mixed prototype refuses weights shared across precision groups')
 def _for_module(self,module):return self._mlp_kernels if id(module) in self._mlp_ids else self.kernels
 def _group(self,modules):
  selected=[self._for_module(m) for m in modules]
  if any(k is not selected[0] for k in selected):raise ReferenceArithmeticError('Mixed projection group spans precisions')
  return selected[0]
 def _generation_begin(self):
  self._check_kernel_configuration();self._refresh_roles()
  self.kernels._begin_request(m.weight for m in attention_modules(self.model))
  self._mlp_kernels._begin_request(m.weight for m in mlp_modules(self.model))
 def _generation_end(self):
  try:super()._generation_end()
  finally:
   self._mlp_kernels._end_request()
   import torch
   torch.cuda.current_stream(self.device).synchronize()
 def buffers(self,*args,**kwargs):
  other=() if not hasattr(self,'_mlp_kernels') else self._mlp_kernels.weight_metadata_buffers()
  return chain(super().buffers(*args,**kwargs),other)
 def forward_batch(self,*args,**kwargs):
  self._refresh_roles();return super().forward_batch(*args,**kwargs)
 def forward_tokens(self,*args,**kwargs):
  self._refresh_roles();return super().forward_tokens(*args,**kwargs)
 def _project(self,value,module,flag):
  return self._for_module(module).linear(value,module.weight,getattr(module,'bias',None),error_flag=flag)
 def _project_many(self,value,modules,flag):
  return self._group(modules).linear_many(value,tuple(m.weight for m in modules),tuple(getattr(m,'bias',None) for m in modules),error_flag=flag)
 def _prefill_norm_project_many(self,hidden,norm,epsilon,modules,flag):
  k=self._group(modules)
  weights,biases=tuple(m.weight for m in modules),tuple(getattr(m,'bias',None) for m in modules)
  if hidden.shape[0]==1:return k.linear_many(k.rms_norm(hidden,norm,epsilon,error_flag=flag),weights,biases,error_flag=flag)
  return k.linear_many(None,weights,biases,error_flag=flag,prepared=k.rms_norm_quantized(hidden,norm,epsilon,error_flag=flag))
 def _decode_norm_project_many(self,hidden,norm,epsilon,modules,flag):
  k=self._group(modules);weights,biases=tuple(m.weight for m in modules),tuple(getattr(m,'bias',None) for m in modules)
  if hidden.shape[0]==1:return k.linear_many(k.rms_norm(hidden,norm,epsilon,error_flag=flag),weights,biases,error_flag=flag,decode_target_ctas_per_sm=self._decode_target)
  return k.linear_many(None,weights,biases,error_flag=flag,decode_target_ctas_per_sm=self._decode_target,prepared=k.rms_norm_quantized(hidden,norm,epsilon,error_flag=flag))
 def _decode_gated_project(self,gate,up,module,flag):
  k=self._for_module(module)
  if gate.shape[0]>1 and gate.shape[1]<=12288:
   return k.linear_decode(None,module.weight,getattr(module,'bias',None),error_flag=flag,target_ctas_per_sm=self._decode_target,prepared=k.silu_mul_quantized(gate,up,error_flag=flag))
  return k.linear_decode(k.silu_mul(gate,up,error_flag=flag),module.weight,getattr(module,'bias',None),error_flag=flag,target_ctas_per_sm=self._decode_target)
 def _decode_residual_project(self,hidden,value,module,flag):
  return self._for_module(module).linear_decode(value,module.weight,getattr(module,'bias',None),error_flag=flag,target_ctas_per_sm=self._decode_target,residual=hidden)
 def _decode_mlp(self,hidden,layer,epsilon,flag):
  if hidden.shape[0]==1:return StrictDecoderGraph._decode_mlp(self,hidden,layer,epsilon,flag)
  k,mlp=self._mlp_kernels,layer.mlp
  prepared=k.rms_norm_quantized(hidden,layer.post_attention_layernorm.weight,epsilon,error_flag=flag)
  biases=(getattr(mlp.gate_proj,'bias',None),getattr(mlp.up_proj,'bias',None))
  planes=k.gate_up_silu_quantized(prepared,mlp.gate_proj.weight,mlp.up_proj.weight,biases,error_flag=flag,decode_target_ctas_per_sm=self._decode_target)
  if planes is None:
   gate,up=k.linear_many(None,(mlp.gate_proj.weight,mlp.up_proj.weight),biases,error_flag=flag,decode_target_ctas_per_sm=self._decode_target,prepared=prepared)
   if gate.shape[1]>12288:return self._decode_residual_project(hidden,k.silu_mul(gate,up,error_flag=flag),mlp.down_proj,flag)
   planes=k.silu_mul_quantized(gate,up,error_flag=flag)
  return k.linear_decode(None,mlp.down_proj.weight,getattr(mlp.down_proj,'bias',None),error_flag=flag,target_ctas_per_sm=self._decode_target,prepared=planes,residual=hidden)
