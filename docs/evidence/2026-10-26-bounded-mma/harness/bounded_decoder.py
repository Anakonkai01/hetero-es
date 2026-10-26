"""Unselected bounded half-integer projections with the unchanged B22 LM head."""
import hashlib
from itertools import chain
from pathlib import Path

from heteroes.canonical import canonical_json_hash
from heteroes.eval import integer_reference
from heteroes.eval.integer_cuda import IntegerCudaKernels, static_identity
from heteroes.eval.integer_decoder import IntegerDecoderGraph, IntegerDecoderReference
from bounded_reference import block_length, linear
from half2_cuda import Half2BoundedKernels


def arithmetic(a,w):
    return {'operator':'bounded_half_integer_dot_v1_probe','activationBits':a,'weightBits':w,
            'blockK':block_length(a,w),'partialMagnitudeAtMost':2**24,
            'rounding':'row_power2_integer_rne_exact_dot_then_f32_rne_signed_ftz',
            'weightStorage':'live_fp16','hardwareQualified':False}


def compose(identity,backend,a,w):
    return {**identity,'backend':backend,
            'operators':{**identity['operators'],'linear':arithmetic(a,w),'lmHead':integer_reference.identity(22)},
            'boundedDecoderSourceSha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'hardwareQualified':False}


class BoundedDecoderReference(IntegerDecoderReference):
    def __init__(self,model,*,activation_bits=8,weight_bits=8,**kwargs):
        block_length(activation_bits,weight_bits)
        self.activation_bits,self.weight_bits=activation_bits,weight_bits
        super().__init__(model,magnitude_bits=22,**kwargs)
        self.identity=compose(self.identity,'decoder_bounded_half_integer_reference_v1_probe',activation_bits,weight_bits)
        self.fingerprint=canonical_json_hash(self.identity)

    def _linear(self,value,module):
        if module is self.model.lm_head:
            return super()._linear(value,module)
        return linear(value,module.weight,getattr(module,'bias',None),activation_bits=self.activation_bits,
                      weight_bits=self.weight_bits)


class BoundedDecoderGraph(IntegerDecoderGraph):
    def __init__(self,model,*,activation_bits=8,weight_bits=8,**kwargs):
        block_length(activation_bits,weight_bits)
        super().__init__(model,magnitude_bits=14,**kwargs)
        budget=self.kernels.max_partial_bytes
        self.kernels=Half2BoundedKernels(self.device,activation_bits=activation_bits,weight_bits=weight_bits,
                                       max_partial_bytes=budget)
        self.head_kernels=IntegerCudaKernels(self.device,magnitude_bits=22,max_partial_bytes=budget)
        self._kernel_configuration=self._current_kernel_configuration()
        self.identity={**compose(self.identity,'decoder_bounded_half_integer_graph_v1_probe',activation_bits,weight_bits),
                       'kernels':{'bounded':self.kernels.arithmetic(),'head':static_identity(22,budget)},
                       'weightQuantization':'packed_half2_magic_rne_v1_probe'}
        self.fingerprint=canonical_json_hash(self.identity)

    def _current_kernel_configuration(self):
        head=getattr(self,'head_kernels',None)
        return (*super()._current_kernel_configuration(),
                *(getattr(self.kernels,name,None)for name in ('activation_bits','weight_bits','block_k')),
                None if head is None else (head.magnitude_bits,head.max_partial_bytes,head.weight_load,head.device))

    def _project(self,value,module,flag):
        kernel=self.head_kernels if module is self.model.lm_head else self.kernels
        return kernel.linear(value,module.weight,getattr(module,'bias',None),error_flag=flag)

    def _decode_project(self,value,module,flag):
        kernel=self.head_kernels if module is self.model.lm_head else self.kernels
        return kernel.linear_decode(value,module.weight,getattr(module,'bias',None),error_flag=flag,
                                    target_ctas_per_sm=self._decode_target)

    def _generation_begin(self):
        self._check_kernel_configuration()
        self.kernels._begin_request(w for w in self._projection_weights()if w is not self.model.lm_head.weight)
        self.head_kernels._begin_request((self.model.lm_head.weight,))

    def _generation_end(self):
        self.head_kernels._end_request()
        super()._generation_end()

    def buffers(self,*args,**kwargs):
        return chain(super().buffers(*args,**kwargs),self.head_kernels.weight_metadata_buffers())

    def kernel_identity(self):
        return {'bounded':self.kernels.identity(),'head':self.head_kernels.identity()}
