"""Unselected 16-byte raw FP16 prefetch with four-lane shared tile redistribution."""
import hashlib
from pathlib import Path

from heteroes.canonical import canonical_json_hash
from heteroes.eval import integer_cuda as ic

_COPY = r'''
#if WEIGHT_PREFETCH
__device__ __forceinline__ void prefetch_half_tile(unsigned* destination,const u16* w,
                                                  int n,int outputs,int start,int thread) {
  int k=start+thread*8;
#if WIDTH % 8 == 0
  if((((unsigned long long)w)&15ull)==0ull) {
    int valid=(n<outputs && k+7<WIDTH) ? 16 : 0;
    const u16* pointer=valid ? w+(size_t)n*WIDTH+k : w;
    unsigned long long address;
    asm volatile("cvta.to.shared.u64 %0, %1;" : "=l"(address) : "l"(destination));
    asm volatile("cp.async.ca.shared.global [%0], [%1], 16, %2;" ::
                 "r"((unsigned)address), "l"(pointer), "r"(valid) : "memory");
  } else
#endif
  {
    #pragma unroll
    for(int i=0;i<4;++i) {
      unsigned halves=0;
      if(n<outputs) {
        if(k+i*2<WIDTH)halves=(unsigned)w[(size_t)n*WIDTH+k+i*2];
        if(k+i*2+1<WIDTH)halves|=((unsigned)w[(size_t)n*WIDTH+k+i*2+1])<<16;
      }
      destination[i]=halves;
    }
  }
}
#endif

'''


class Prefetch16Kernels(ic.IntegerCudaKernels):
    def _integer_functions(self, width, has_bias=False, row_tile=16, warps=4, split_k=1, *, packed_input=False):
        name=f'prefetch16-{self.magnitude_bits}-{width}-bias{int(has_bias)}-m{row_tile}-w{warps}-s{split_k}-p{int(packed_input)}'
        if name not in self._functions:
            source=ic._SOURCE
            start=source.index('#if WEIGHT_PREFETCH\n// Each lane')
            end=source.index('extern "C" __global__ void integer_input(',start)
            source=source[:start]+_COPY+source[end:]
            old='''      asm volatile("cp.async.wait_group 0;" ::: "memory");
      unsigned current[4];
      #pragma unroll
      for(int i=0;i<4;++i)current[i]=raw_shared[phase][threadIdx.x][i];'''
            new='''      asm volatile("cp.async.wait_group 0;" ::: "memory");
      asm volatile("bar.warp.sync 0xffffffff;" ::: "memory");
      unsigned current[4];
      #pragma unroll
      for(int word=0;word<2;++word) {
        #pragma unroll
        for(int pair=0;pair<2;++pair)
          current[word*2+pair]=raw_shared[phase][warp*32+group*4+(thread>>1)+word*2][(thread&1)*2+pair];
      }'''
            assert source.count(old)==1
            source=source.replace(old,new)
            old='''    // Includes the last zero-filled lookahead and split partitions with no live K tile.
    asm volatile("cp.async.wait_group 0;" ::: "memory");'''
            assert source.count(old)==1
            source=source.replace(old,old+'\n    asm volatile("bar.warp.sync 0xffffffff;" ::: "memory");')
            defines=dict(WIDTH=width,MAGNITUDE_BITS=self.magnitude_bits,DIGITS=2 if self.magnitude_bits==14 else 3,
                         HAS_BIAS=int(has_bias),M_GROUPS=row_tile//16,WARPS=warps,SPLIT_K=split_k,
                         PACKED_INPUT=int(packed_input),WEIGHT_READ32=0,WEIGHT_PREFETCH=1)
            header=''.join(f'#define {k} {v}\n' for k,v in defines.items())
            self._functions[name]=self._compile(name,header+source,
                ['integer_input','integer_weights','integer_linear','integer_simt','integer_finish'],integer_mma=True)
        return self._functions[name]

    def identity(self):
        identity={**super().identity(),'execution':'raw_half_prefetch16_warp4_probe',
                  'weightLoadEffective':'prefetch16_warp4_probe',
                  'prototypeSourceSha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
        identity['fingerprint']=canonical_json_hash({k:v for k,v in identity.items() if k!='fingerprint'})
        return identity
