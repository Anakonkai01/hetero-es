"""Unselected exact B14/B22 two-stage raw FP16 tile prefetch using bounded shared storage."""
import hashlib
from pathlib import Path

from heteroes.canonical import canonical_json_hash
from heteroes.eval import integer_cuda as ic

_PREFETCH = r'''
__device__ __forceinline__ void prefetch_half_tile(unsigned* destination,const u16* w,
                                                  int n,int outputs,int start,int thread) {
  #pragma unroll
  for(int word=0;word<2;++word) {
    int k=start+thread*4+word*16;
#if WIDTH % 4 == 0
    if((((unsigned long long)w)&7ull)==0ull) {
      int valid=(n<outputs && k+3<WIDTH) ? 8 : 0;
      const u16* pointer=valid ? w+(size_t)n*WIDTH+k : w;
      unsigned long long address;
      asm volatile("cvta.to.shared.u64 %0, %1;" : "=l"(address) : "l"(destination+word*2));
      asm volatile("cp.async.ca.shared.global [%0], [%1], 8, %2;" ::
                   "r"((unsigned)address), "l"(pointer), "r"(valid) : "memory");
    } else
#endif
    {
      unsigned lo=0,hi=0;
      if(n<outputs) {
        if(k<WIDTH)lo=(unsigned)w[(size_t)n*WIDTH+k];
        if(k+1<WIDTH)lo|=((unsigned)w[(size_t)n*WIDTH+k+1])<<16;
        if(k+2<WIDTH)hi=(unsigned)w[(size_t)n*WIDTH+k+2];
        if(k+3<WIDTH)hi|=((unsigned)w[(size_t)n*WIDTH+k+3])<<16;
      }
      destination[word*2]=lo;destination[word*2+1]=hi;
    }
  }
}
'''


class PrefetchKernels(ic.IntegerCudaKernels):
    def _integer_functions(self,width,has_bias=False,row_tile=16,warps=4,split_k=1,*,packed_input=False):
        name=f'prefetch-{self.magnitude_bits}-{width}-bias{int(has_bias)}-m{row_tile}-w{warps}-s{split_k}-p{int(packed_input)}'
        if name not in self._functions:
            source=ic._SOURCE
            position=source.index('extern "C" __global__ void integer_input(')
            source=source[:position]+_PREFETCH+source[position:]
            target='  int column=blockIdx.x*(WARPS*8)+warp*8;'
            assert source.count(target)==1
            source=source.replace(target,target+'\n  __shared__ unsigned raw_shared[2][32*WARPS][4];')
            target='    for(int chunk=blockIdx.z;chunk<(WIDTH+31)/32;chunk+=SPLIT_K) {'
            assert source.count(target)==1
            replacement=r'''    int phase=0;
    prefetch_half_tile(raw_shared[0][threadIdx.x],w,column+group,outputs,blockIdx.z*32,thread);
    asm volatile("cp.async.commit_group;" ::: "memory");
    for(int chunk=blockIdx.z;chunk<(WIDTH+31)/32;chunk+=SPLIT_K) {
      asm volatile("cp.async.wait_group 0;" ::: "memory");
      unsigned current[4];
      #pragma unroll
      for(int i=0;i<4;++i)current[i]=raw_shared[phase][threadIdx.x][i];
      phase^=1;
      prefetch_half_tile(raw_shared[phase][threadIdx.x],w,column+group,outputs,(chunk+SPLIT_K)*32,thread);
      asm volatile("cp.async.commit_group;" ::: "memory");'''
            source=source.replace(target,replacement)
            start=source.index('#if WEIGHT_READ32')
            end=source.index('#endif',start)+len('#endif')
            replacement=r'''        #pragma unroll
        for(int pair=0;pair<2;++pair) {
          unsigned halves=current[word*2+pair];
          pack_digits(packed,quant_half((u16)halves,exponent),pair*2);
          pack_digits(packed,quant_half((u16)(halves>>16),exponent),pair*2+1);
        }'''
            source=source[:start]+replacement+source[end:]
            target='    #pragma unroll\n    for(int m=0;m<M_GROUPS;++m) {'
            assert source.count(target)==1
            source=source.replace(target,'    asm volatile("cp.async.wait_group 0;" ::: "memory");\n'+target)
            defines=dict(WIDTH=width,MAGNITUDE_BITS=self.magnitude_bits,DIGITS=2 if self.magnitude_bits==14 else 3,
                         HAS_BIAS=int(has_bias),M_GROUPS=row_tile//16,WARPS=warps,SPLIT_K=split_k,
                         PACKED_INPUT=int(packed_input),WEIGHT_READ32=0)
            header=''.join(f'#define {k} {v}\n' for k,v in defines.items())
            self._functions[name]=self._compile(name,header+source,
                ['integer_input','integer_weights','integer_linear','integer_simt','integer_finish'],integer_mma=True)
        return self._functions[name]

    def identity(self):
        identity={**super().identity(),'execution':'raw_half_two_stage_cp_async_probe',
                  'prototypeSourceSha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
        identity['fingerprint']=canonical_json_hash({k:v for k,v in identity.items() if k!='fingerprint'})
        return identity
