"""Unselected asymmetric integer projection; live weights remain FP16, no vendor GEMM."""
import hashlib
from pathlib import Path

from heteroes.canonical import canonical_json_hash
from heteroes.eval import integer_cuda as ic


class MixedKernels(ic.IntegerCudaKernels):
    def __init__(self,device,*,activation_bits=22,weight_bits=6,**kwargs):
        if type(weight_bits) is not int or weight_bits not in (6,14,22):
            raise ValueError('Prototype weight precision')
        self.weight_bits=weight_bits
        super().__init__(device,magnitude_bits=activation_bits,**kwargs)

    def mixed_identity(self):
        return {'operator':'row_scaled_mixed_integer_dot_v1_probe','activationBits':self.magnitude_bits,
                'weightBits':self.weight_bits,'weightStorage':'live_fp16','activationLimbs':2 if self.magnitude_bits==14 else 3,
                'weightLimbs':{6:1,14:2,22:3}[self.weight_bits],
                'prototypeSourceSha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                'rounding':'exact_scaled_integer_rne_then_signed_ftz','hardwareQualified':False}

    def identity(self):
        identity={**super().identity(),'mixedPrecision':self.mixed_identity(),
                  'kernel':'row_scaled_mixed_integer_mma_v1_probe','integerKernel':'row_scaled_mixed_integer_mma_v1_probe',
                  'linear':self.mixed_identity(),'integerReference':self.mixed_identity()}
        identity['fingerprint']=canonical_json_hash({k:v for k,v in identity.items() if k!='fingerprint'})
        return identity

    def _integer_functions(self,width,has_bias=False,row_tile=16,warps=4,split_k=1,*,packed_input=False):
        name=f'mixed-a{self.magnitude_bits}-w{self.weight_bits}-k{width}-bias{int(has_bias)}-m{row_tile}-w{warps}-s{split_k}-p{int(packed_input)}'
        if name not in self._functions:
            source=ic._SOURCE
            start=source.index('__device__ __forceinline__ int quant_half(')
            end=source.index('__device__ __forceinline__ void pack_digits(',start)
            source=source[:start]+source[start:end].replace('MAGNITUDE_BITS','WEIGHT_BITS')+source[end:]
            start=source.index('__device__ __forceinline__ void pack_digits(')
            end=source.index('\nextern "C"',start)
            weight_pack=source[start:end].replace('pack_digits','pack_weight_digits').replace('DIGITS','WEIGHT_DIGITS')
            source=source[:end]+'\n'+weight_pack+source[end:]
            start=source.index('      unsigned b[DIGITS][2]')
            end=source.index('      #pragma unroll\n      for(int m=0;m<M_GROUPS;++m)',start)
            section=source[start:end].replace('DIGITS','WEIGHT_DIGITS').replace('pack_digits(','pack_weight_digits(')
            source=source[:start]+section+source[end:]
            source=source.replace('2*DIGITS-1','DIGITS+WEIGHT_DIGITS-1')
            assert source.count('for(int j=0;j<DIGITS;++j)')==1
            source=source.replace('for(int j=0;j<DIGITS;++j)','for(int j=0;j<WEIGHT_DIGITS;++j)')
            assert source.count('-2*(MAGNITUDE_BITS-1)')==3
            source=source.replace('-2*(MAGNITUDE_BITS-1)','-(MAGNITUDE_BITS-1)-(WEIGHT_BITS-1)')
            defines=dict(WIDTH=width,MAGNITUDE_BITS=self.magnitude_bits,WEIGHT_BITS=self.weight_bits,
                         DIGITS=2 if self.magnitude_bits==14 else 3,WEIGHT_DIGITS={6:1,14:2,22:3}[self.weight_bits],
                         HAS_BIAS=int(has_bias),M_GROUPS=row_tile//16,WARPS=warps,SPLIT_K=split_k,
                         PACKED_INPUT=int(packed_input),
                         WEIGHT_READ32=int(ic.weight_read_plan(self.magnitude_bits,self.arch,self.weight_load)=='paired'))
            header=''.join(f'#define {k} {v}\n' for k,v in defines.items())
            self._functions[name]=self._compile(name,header+source,
                ['integer_input','integer_weights','integer_linear','integer_simt','integer_finish'],integer_mma=True)
        return self._functions[name]
