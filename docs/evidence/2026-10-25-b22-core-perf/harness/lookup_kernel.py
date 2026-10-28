"""Scratch B22 hypothesis: a fixed 10 MiB FP16/exponent codec replaces repeated weight digit arithmetic."""
import numpy as np
import torch
from heteroes.eval import integer_cuda as original


def codec(bits):
    half=np.arange(65536,dtype=np.int64)
    exponent=(half>>10)&31
    mantissa=(half&1023)+np.where(exponent==0,0,1024)
    table=np.empty((40,65536),dtype=np.uint32)
    for index,row_exponent in enumerate(range(-24,16)):
        shift=np.where(exponent==0,bits-25-row_exponent,exponent+bits-26-row_exponent)
        right=np.maximum(-shift,0)
        whole=mantissa>>right
        remainder=mantissa&((np.int64(1)<<right)-1)
        halfway=np.int64(1)<<np.maximum(right-1,0)
        rounded=whole+((remainder>halfway)|((remainder==halfway)&((whole&1)!=0)))
        q=np.where(shift>=0,mantissa<<np.maximum(shift,0),rounded)
        q=np.where((half&32768)!=0,-q,q)
        invalid=(exponent==31)|(np.abs(q)>(1<<bits))
        packed=np.zeros(65536,dtype=np.int64)
        for digit in range(2 if bits==14 else 3):
            low=q&255
            signed=np.where(low>=128,low-256,low)
            packed|=low<<(8*digit)
            q=(q-signed)//256
        table[index]=np.where(invalid,np.int64(0x80000000),packed).astype(np.uint32)
    return table


class LookupKernels(original.IntegerCudaKernels):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self._lookup_functions=set()
        self._codec=torch.from_numpy(codec(self.magnitude_bits).view(np.int32)).cuda()

    def _integer_functions(self,width,has_bias=False,row_tile=16,warps=4,split_k=1,*,packed_input=False):
        name=f'lookup-{self.magnitude_bits}-{width}-{int(has_bias)}-m{row_tile}-w{warps}-s{split_k}-p{int(packed_input)}'
        if name not in self._functions:
            source=original._SOURCE
            start=source.index('extern "C" __global__ void __launch_bounds__(32*WARPS)\ninteger_linear')
            end=source.index('// Same arithmetic, different scheduling:')
            body=source[start:end]
            body=body.replace('i64* partials,int rows,int outputs)', 'i64* partials,const unsigned* codec,int rows,int outputs)')
            first=body.index('      unsigned b[DIGITS][2]={};')
            last=body.index('      #pragma unroll\n      for(int m=0;',first)
            packing=r'''
      unsigned b[DIGITS][2]={};
      int n=column+group;
      int exponent=n<outputs ? ew[n] : 0;
      #pragma unroll
      for(int word=0;word<2;++word) {
        unsigned codes[4];
        #pragma unroll
        for(int i=0;i<4;++i) {
          int k=start+thread*4+word*16+i;
          unsigned code=(n<outputs && k<WIDTH) ? codec[(size_t)(exponent+24)*65536+w[(size_t)n*WIDTH+k]] : 0;
          if(code&0x80000000u) { atomicOr(error,1); code=0; }
          codes[i]=code;
        }
        #pragma unroll
        for(int d=0;d<DIGITS;++d) {
          unsigned ab=__byte_perm(codes[0],codes[1],d|((d+4)<<4));
          unsigned cd=__byte_perm(codes[2],codes[3],d|((d+4)<<4));
          b[d][word]=__byte_perm(ab,cd,0x5410);
        }
      }
'''
            body=body[:first]+packing+body[last:]
            source=source[:start]+body+source[end:]
            defines=dict(WIDTH=width,MAGNITUDE_BITS=self.magnitude_bits,DIGITS=2 if self.magnitude_bits==14 else 3,
                         HAS_BIAS=int(has_bias),M_GROUPS=row_tile//16,WARPS=warps,SPLIT_K=split_k,PACKED_INPUT=int(packed_input))
            header=''.join(f'#define {k} {v}\n' for k,v in defines.items())
            self._functions[name]=self._compile(name,header+source,
                ['integer_input','integer_weights','integer_linear','integer_simt','integer_finish'],integer_mma=True)
            self._lookup_functions.add(id(self._functions[name]['integer_linear']))
        return self._functions[name]

    def _launch(self,function,**kwargs):
        if id(function) in self._lookup_functions:
            kwargs['pointers']=(*kwargs['pointers'],self._codec)
        return super()._launch(function,**kwargs)
