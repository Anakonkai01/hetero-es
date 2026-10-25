"""Scratch model composition: asymmetric projections and unchanged B22 LM head."""
from itertools import chain

from heteroes.canonical import canonical_json_hash
from heteroes.eval.integer_cuda import IntegerCudaKernels
from heteroes.eval.integer_decoder import IntegerDecoderGraph
from mixed_cuda import MixedKernels


class MixedDecoderGraph(IntegerDecoderGraph):
    def __init__(self,model,*,activation_bits=22,weight_bits=6,**kwargs):
        super().__init__(model,magnitude_bits=activation_bits,**kwargs)
        self.kernels=MixedKernels(self.device,activation_bits=activation_bits,weight_bits=weight_bits)
        self.head_kernels=IntegerCudaKernels(self.device,magnitude_bits=22)
        self._kernel_configuration=self._current_kernel_configuration()
        contract=self.kernels.mixed_identity()
        self.identity={**self.identity,'backend':'decoder_strict_asymmetric_integer_probe_v1',
                       'operators':{**self.identity['operators'],'linear':contract,
                                    'lmHead':{'activationBits':22,'weightBits':22,'contract':'original_b22'}},
                       'kernels':{'mixed':contract,'head':'original_b22'},'hardwareQualified':False}
        self.fingerprint=canonical_json_hash(self.identity)

    def _project(self,value,module,flag):
        k=self.head_kernels if module is self.model.lm_head else self.kernels
        return k.linear(value,module.weight,getattr(module,'bias',None),error_flag=flag)

    def _decode_project(self,value,module,flag):
        k=self.head_kernels if module is self.model.lm_head else self.kernels
        return k.linear_decode(value,module.weight,getattr(module,'bias',None),error_flag=flag,
                               target_ctas_per_sm=self._decode_target)

    def _generation_begin(self):
        self._check_kernel_configuration()
        self.kernels._begin_request(w for w in self._projection_weights() if w is not self.model.lm_head.weight)
        self.head_kernels._begin_request((self.model.lm_head.weight,))

    def _generation_end(self):
        self.head_kernels._end_request()
        super()._generation_end()

    def buffers(self,*args,**kwargs):
        return chain(super().buffers(*args,**kwargs),self.head_kernels.weight_metadata_buffers())

    def kernel_identity(self):
        return {'mixed':self.kernels.identity(),'head':self.head_kernels.identity()}
