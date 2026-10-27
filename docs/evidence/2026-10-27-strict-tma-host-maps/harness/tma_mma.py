"""Unselected B22 projection with only the operand transport replaced by swizzled TMA transactions."""
import torch
from heteroes.eval import integer_cuda as ic
from audit import TmaOwner
from tensor_map import maps
from pipeline_copy import HELPERS

def once(s,old,new):
    assert s.count(old)==1,old
    return s.replace(old,new)

def source(width,columns,split,stages,min_blocks,has_bias):
    start=ic._SOURCE.index('__device__ __forceinline__ void stream_body(')
    end=ic._SOURCE.index('#if STREAM_MIN_BLOCKS > 1',start)
    body=ic._SOURCE[start:end]
    body=once(body,'void stream_body(','void tma_stream_body(')
    body=once(body,'const qi_t* x,const u16* w,const u16* bias',
              'const qi_t* x,const u16* w,const void* wd,const void* ad,const u16* bias')
    body=body.replace('__align__(16)','__align__(1024)')
    body=once(body,'  int lane=threadIdx.x&31,','  __shared__ __align__(8) unsigned long long barriers[STAGES];\n  __shared__ int failed;\n  int lane=threadIdx.x&31,')
    old='    int accum[M_GROUPS][JN][2*DIGITS-1][4]={};'
    body=once(body,old,old+r'''
    if(threadIdx.x==0) {
      failed=0;
      for(int s=0;s<STAGES;++s) tma_init(barriers+s);
      asm volatile("fence.proxy.async.shared::cta;" ::: "memory");
    }
    __syncthreads();
''')
    old=r'''    #pragma unroll
    for(int s=0;s<STAGES-1;++s) {
      if(s<count) stream_stage(weights_shared[s],inputs_shared[s],x,w,rows,outputs,first,column0,(begin+s)*KS);
      asm volatile("cp.async.commit_group;" ::: "memory");
    }'''
    body=once(body,old,r'''    if(threadIdx.x==0) for(int s=0;s<STAGES-1;++s)
      if(s<count) tma_stage(weights_shared[s],inputs_shared[s],wd,ad,barriers+s,(begin+s)*KS,column0,first);''')
    old=r'''      asm volatile("cp.async.wait_group %0;" :: "n"(STAGES-2) : "memory");
      __syncthreads();'''
    body=once(body,old,r'''      unsigned ready=tma_wait(barriers+it%STAGES,(it/STAGES)&1);
      if(!ready) atomicExch(&failed,1);
      __syncthreads();
      if(failed) {if(threadIdx.x==0) atomicOr(error,4);return;}''')
    old=r'''      if(next<count) stream_stage(weights_shared[next%STAGES],inputs_shared[next%STAGES],x,w,rows,outputs,first,
                                  column0,(begin+next)*KS);
      asm volatile("cp.async.commit_group;" ::: "memory");'''
    body=once(body,old,r'''      if(threadIdx.x==0 && next<count)
        tma_stage(weights_shared[next%STAGES],inputs_shared[next%STAGES],wd,ad,barriers+next%STAGES,
                  (begin+next)*KS,column0,first);''')
    body=once(body,'    asm volatile("cp.async.wait_group 0;" ::: "memory");\n','')
    body=body.replace('stream_weight_swizzle(r)','(r&7)').replace('stream_input_swizzle(row)','((row>>1)&3)')
    entry=r'''
#if STREAM_MIN_BLOCKS > 1
extern "C" __global__ void __launch_bounds__(128,STREAM_MIN_BLOCKS)
#else
extern "C" __global__ void __launch_bounds__(128)
#endif
tma_stream(const qi_t* x,const u16* w,const void* wd,const void* ad,const u16* bias,const int* ex,const int* ew,
           float* out,int* error,i64* partials,int rows,int outputs) {
  tma_stream_body(x,w,wd,ad,bias,ex,ew,out,error,partials,rows,outputs,blockIdx.x*NT,outputs,0);
}
'''
    defines={'WIDTH':width,'MAGNITUDE_BITS':22,'DIGITS':3,'HAS_BIAS':int(has_bias),'M_GROUPS':2,'WARPS':4,
             'SPLIT_K':split,'PACKED_INPUT':1,'WEIGHT_READ32':0,'WEIGHT_PREFETCH':1,'FAST_CONVERT':1,
             'STREAM_LDSM_INPUT':1,'JN':columns//32,'STAGES':stages,'STREAM_MIN_BLOCKS':min_blocks}
    header=''.join(f'#define {k} {v}\n' for k,v in defines.items())
    return header+ic._SOURCE+HELPERS+body+entry

class TmaMma:
    def __init__(self,width,columns=32,split=1,stages=3,min_blocks=0,has_bias=False):
        self.context=torch.empty(1,device='cuda');self.k=TmaOwner('cuda',magnitude_bits=22)
        assert self.k.arch=='sm_120' and width%16==0 and stages in (2,3) and columns in (32,64)
        self.width,self.columns,self.split,self.has_bias=width,columns,split,has_bias
        self.name=f'tma-mma-v1-k{width}-n{columns}-s{split}-st{stages}-r{min_blocks}-b{int(has_bias)}'
        self.functions=self.k._compile(self.name,source(width,columns,split,stages,min_blocks,has_bias),['tma_stream','integer_finish'],integer_mma=True)
    def project(self,prepared,weight,ew,flag,bias=None,*,descriptors=None):
        planes,ex=prepared;rows=ex.numel();outputs=weight.shape[0]
        assert rows<=65535*32
        wd,ad=maps(self.k,weight,planes,rows,self.width,self.columns) if descriptors is None else descriptors
        out=torch.empty((rows,outputs),dtype=torch.float32,device=weight.device)
        partials=torch.empty((self.split,rows,outputs),dtype=torch.int64,device=weight.device) if self.split>1 else out
        b=weight if bias is None else bias
        self.k._launch(self.functions['tma_stream'],grid=(-(-outputs//self.columns),-(-rows//32),self.split),block=(128,1),
                       pointers=(planes,weight,wd,ad,b,ex,ew,out,flag,partials),integers=(rows,outputs))
        if self.split>1:
            self.k._launch(self.functions['integer_finish'],grid=(-(-outputs//256),rows),block=(256,1),
                           pointers=(partials,b,ex,ew,out,flag),integers=(rows,outputs))
        return out
    def linear(self,value,weight,bias=None):
        flag=self.k.new_error_flag();prepared=self.k.quantize_input(value,_packed=True,error_flag=flag)
        ew=self.k._weight_exponents(weight,flag)
        return self.project(prepared,weight,ew,flag,bias),flag
