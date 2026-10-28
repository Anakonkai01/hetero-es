"""Unselected 256-thread streamed B22 tile: two four-warp groups own disjoint 32-row slices."""
import torch
from heteroes.eval import integer_cuda as ic

def once(s,old,new):
    assert s.count(old)==1,(old,s.count(old))
    return s.replace(old,new)

def source(width,split,stages,resident,has_bias):
    s=ic._SOURCE
    s=once(s,'#define MT (M_GROUPS*16)','#define MT 64')
    s=once(s,'for(int i=0;i<NT*8/128;++i)', 'for(int i=0;i<NT*8/256;++i)')
    s=once(s,'int c=tid+i*128, r=c>>3','int c=tid+i*256, r=c>>3')
    s=once(s,'for(int c=tid;c<DIGITS*MT*4;c+=128)','for(int c=tid;c<DIGITS*MT*4;c+=256)')
    prefix,body=s.split('__device__ __forceinline__ void stream_body(',1)
    body=once(body,'int lane=threadIdx.x&31, warp=threadIdx.x>>5, group=lane>>2, thread=lane&3;',
                   'int lane=threadIdx.x&31, warp=(threadIdx.x>>5)&3, warp_m=threadIdx.x>>7, group=lane>>2, thread=lane&3;')
    s=prefix+'__device__ __forceinline__ void stream_body('+body
    s=once(s,'int row=m*16+(lane&15), chunk=step*2+(lane>>4);',
             'int row=warp_m*32+m*16+(lane&15), chunk=step*2+(lane>>4);')
    s=once(s,'int row=first+m*16+group+(d>>1)*8, n=column0+warp*8*JN+j*8+thread*2+(d&1);',
             'int row=first+warp_m*32+m*16+group+(d>>1)*8, n=column0+warp*8*JN+j*8+thread*2+(d&1);')
    entry=r'''
#if STREAM_MIN_BLOCKS > 1
extern "C" __global__ void __launch_bounds__(256,STREAM_MIN_BLOCKS)
#else
extern "C" __global__ void __launch_bounds__(256)
#endif
integer_m64(const qi_t* x,const u16* w,const u16* bias,const int* ex,const int* ew,
            float* out,int* error,i64* partials,int rows,int outputs) {
  stream_body(x,w,bias,ex,ew,out,error,partials,rows,outputs,blockIdx.x*NT,outputs,0);
}
'''
    defines=dict(WIDTH=width,MAGNITUDE_BITS=22,DIGITS=3,HAS_BIAS=int(has_bias),M_GROUPS=2,WARPS=8,
                 SPLIT_K=split,PACKED_INPUT=1,WEIGHT_READ32=0,WEIGHT_PREFETCH=1,FAST_CONVERT=1,
                 STREAM_LDSM_INPUT=1,JN=1,STAGES=stages,STREAM_MIN_BLOCKS=resident)
    return ''.join(f'#define {k} {v}\n' for k,v in defines.items())+s+entry

class M64:
    def __init__(self,width,split=1,stages=2,resident=2,has_bias=False):
        self.context=torch.empty(1,device='cuda');self.k=ic.IntegerCudaKernels('cuda',magnitude_bits=22)
        assert self.k.arch=='sm_120' and width%16==0
        self.width,self.split=width,split
        self.name=f'warp-m64-v1-k{width}-s{split}-st{stages}-r{resident}-b{int(has_bias)}'
        self.functions=self.k._compile(self.name,source(width,split,stages,resident,has_bias),['integer_m64','integer_finish'],integer_mma=True)
    def project(self,prepared,weight,ew,flag,bias=None):
        planes,ex=prepared;rows=ex.numel();outputs=weight.shape[0]
        out=torch.empty((rows,outputs),device=weight.device)
        partials=torch.empty((self.split,rows,outputs),device=weight.device,dtype=torch.int64) if self.split>1 else out
        b=weight if bias is None else bias
        self.k._launch(self.functions['integer_m64'],grid=(-(-outputs//32),-(-rows//64),self.split),block=(256,1),
                       pointers=(planes,weight,b,ex,ew,out,flag,partials),integers=(rows,outputs))
        if self.split>1:
            self.k._launch(self.functions['integer_finish'],grid=(-(-outputs//256),rows),block=(256,1),
                           pointers=(partials,b,ex,ew,out,flag),integers=(rows,outputs))
        return out
    def linear(self,x,w,bias=None):
        flag=self.k.new_error_flag();prepared=self.k.quantize_input(x,_packed=True,error_flag=flag)
        return self.project(prepared,w,self.k._weight_exponents(w,flag),flag,bias),flag
