"""Unselected coalesced warp attention preserving every strict rounded tree node."""
import hashlib
from pathlib import Path
from heteroes.eval import strict_cuda as sc

_BODY=r'''
__device__ __forceinline__ float warp_tree(float v,int valid,unsigned& bad) {
  int lane=threadIdx.x&31;
  #pragma unroll
  for(int stride=1;stride<32;stride<<=1) {
    float other=__shfl_down_sync(0xffffffffu,v,stride);
    if((lane&(2*stride-1))==0 && lane+stride<valid)v=add_(v,other,bad);
  }
  return v;
}
extern "C" __global__ void warp_attention(const float* q,const float* key,const float* value,float* out,
    int* error,const int* ranges,int heads,int length,int total_keys,int past,int repeats,int dim,int packed,float scale) {
  const int i=blockIdx.x,kv=blockIdx.y,h=kv*repeats+blockIdx.z;
  const int start=packed?ranges[3*i]:0,keys=packed?ranges[3*i+1]:total_keys;
  const int limit=packed?ranges[3*i+2]:past+i;
  const int lane=threadIdx.x&31,warp=threadIdx.x>>5;
  extern __shared__ float shared[];
  float* query=shared;
  float* numerators=query+DIM;
  float* scratch=numerators+keys;
  __shared__ float maxima[8],inverse_shared;
  unsigned bad=0;
  for(int d=threadIdx.x;d<DIM;d+=THREADS)query[d]=load(q+((size_t)h*length+i)*DIM+d,bad);
  __syncthreads();
  float local=-FLT_BIG;
  for(int j=warp;j<keys;j+=WARPS) {
    Tree tree;tree.n=0;
    #pragma unroll
    for(int first=0;first<DIM;first+=32) {
      const int valid=DIM-first<32?DIM-first:32;
      float term=0.0f;
      if(lane<valid)term=mul_(query[first+lane],load(key+((size_t)kv*total_keys+start+j)*DIM+first+lane,bad),bad);
      term=warp_tree(term,valid,bad);
      if(lane==0)push(tree,term,bad);
    }
    if(lane==0) {
      float score=mul_(finish(tree,bad),scale,bad);
      numerators[j]=score;
      if(j<=limit && score>local)local=score;
    }
  }
  if(lane==0)maxima[warp]=local;
  __syncthreads();
  float maximum=-FLT_BIG;
  #pragma unroll
  for(int w=0;w<WARPS;++w)maximum=maxima[w]>maximum?maxima[w]:maximum;
  if(__float_as_uint(maximum)==0x80000000u)maximum=0.0f;
  for(int j=threadIdx.x;j<keys;j+=THREADS) {
    bool allowed=j<=limit;
    float e=exp_(add_(allowed?numerators[j]:maximum,-maximum,bad),bad);
    numerators[j]=allowed?e:0.0f;
    scratch[j]=numerators[j];
  }
  __syncthreads();
#if FULL
  int padded=1;while(padded<keys)padded<<=1;
  int chunk=padded/WARPS;if(chunk<32)chunk=32;
  Tree sum;sum.n=0;
  for(int first=warp*chunk;first<keys && first<(warp+1)*chunk;first+=32) {
    int valid=keys-first<32?keys-first:32;
    float term=lane<valid?numerators[first+lane]:0.0f;
    term=warp_tree(term,valid,bad);
    if(lane==0)push(sum,term,bad);
  }
  if(lane==0 && warp*chunk<keys)maxima[warp]=finish(sum,bad);
  __syncthreads();
  if(threadIdx.x==0) {
    Tree merged;merged.n=0;
    #pragma unroll
    for(int w=0;w<WARPS;++w)if(w*chunk<keys)push(merged,maxima[w],bad);
    float denominator=finish(merged,bad);
    inverse_shared=reciprocal_(denominator==0.0f?1.0f:denominator,bad);
  }
  __syncthreads();
  float inverse=inverse_shared;
#else
  block_tree(scratch,keys,bad);
  float denominator=scratch[0];
  float inverse=reciprocal_(denominator==0.0f?1.0f:denominator,bad);
#endif
  for(int j=threadIdx.x;j<keys;j+=THREADS)numerators[j]=mul_(numerators[j],inverse,bad);
  __syncthreads();
#if FULL
  int channel=threadIdx.x&(PAD_DIM-1),group=threadIdx.x/PAD_DIM;
  int outchunk=padded/OUT_GROUPS;if(outchunk<1)outchunk=1;
  if(channel<DIM && group*outchunk<keys) {
    Tree t;t.n=0;
    for(int first=group*outchunk;first<keys && first<(group+1)*outchunk;first+=8) {
      int end=(group+1)*outchunk<keys?(group+1)*outchunk:keys;
      int valid=end-first<8?end-first:8;
      float terms[8]={};
      #pragma unroll
      for(int item=0;item<8;++item)if(item<valid)
        terms[item]=mul_(numerators[first+item],load(value+((size_t)kv*total_keys+start+first+item)*DIM+channel,bad),bad);
      #pragma unroll
      for(int stride=1;stride<8;stride<<=1) {
        #pragma unroll
        for(int item=0;item<8;item+=2*stride)
          if(item+stride<valid)terms[item]=add_(terms[item],terms[item+stride],bad);
      }
      push(t,terms[0],bad);
    }
    scratch[group*PAD_DIM+channel]=finish(t,bad);
  }
  __syncthreads();
  if(group==0 && channel<DIM) {
    Tree t;t.n=0;
    #pragma unroll
    for(int g=0;g<OUT_GROUPS;++g)if(g*outchunk<keys)push(t,scratch[g*PAD_DIM+channel],bad);
    out[(size_t)i*heads*DIM+h*DIM+channel]=finish(t,bad);
  }
#else
  for(int d=threadIdx.x;d<DIM;d+=THREADS) {
    Tree t;t.n=0;
    for(int first=0;first<keys;first+=8) {
      int valid=keys-first<8?keys-first:8;
      float terms[8]={};
      #pragma unroll
      for(int item=0;item<8;++item)if(item<valid)
        terms[item]=mul_(numerators[first+item],load(value+((size_t)kv*total_keys+start+first+item)*DIM+d,bad),bad);
      #pragma unroll
      for(int stride=1;stride<8;stride<<=1) {
        #pragma unroll
        for(int item=0;item<8;item+=2*stride)if(item+stride<valid)terms[item]=add_(terms[item],terms[item+stride],bad);
      }
      push(t,terms[0],bad);
    }
    out[(size_t)i*heads*DIM+h*DIM+d]=finish(t,bad);
  }
#endif
  report(error,bad);
}
'''

class WarpAttentionKernels(sc.StrictCudaKernels):
    def __init__(self,device,*,mode='full'):
        if mode not in ('score','full'):raise ValueError('Unknown warp attention mode')
        super().__init__(device);self.mode=mode

    def _functions_for(self,dim):
        name=f'warp-attention-{dim}-{self.mode}'
        if name not in self._functions:
            padded=1<<(dim-1).bit_length();threads=max(128,padded)
            header=''.join(f'#define {k} {v}\n'for k,v in {
                'DIM':dim,'PAD_DIM':padded,'THREADS':threads,'WARPS':threads//32,
                'OUT_GROUPS':threads//padded,'FULL':int(self.mode=='full')}.items())
            constants=''.join(f'#define {k} 0x{v:08x}u\n'for k,v in sc.reference_constants().items())
            helpers=sc._OPS_SOURCE.split('extern "C" __global__ void strict_rms_norm')[0]
            self._functions[name]=self._compile(name,header+constants+helpers+_BODY,['warp_attention'],
                                                ptx_exact=sc.OPS_PTX_EXACT,sass_exact=sc.OPS_SASS_EXACT)
        return self._functions[name]['warp_attention']

    def _launch(self,function,*,grid,block,pointers,integers=(),floats=(),shared=0):
        if len(integers)==7 and len(pointers)==6:
            dim=integers[5];function=self._functions_for(dim)
            threads=max(128,1<<(dim-1).bit_length())
            block=(threads,1)
            max_keys=(shared//4-dim)//2
            shared=4*(dim+max_keys+max(max_keys,threads))
        return super()._launch(function,grid=grid,block=block,pointers=pointers,integers=integers,floats=floats,shared=shared)

    def identity(self):
        return {**super().identity(),'attentionProbe':self.mode,
                'attentionProbeSourceSha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
