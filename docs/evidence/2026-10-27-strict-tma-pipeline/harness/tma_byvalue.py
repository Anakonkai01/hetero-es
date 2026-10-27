"""Second prototype: pass immutable tensor maps in kernel parameters, with no device descriptor copy."""
import ctypes
import numpy as np
import torch
from heteroes.eval import strict_cuda as sc
from audit import TmaOwner
from tma_mma import TmaMma, source as pointer_source, once

def encode_host(k,value,dims,strides,box,*,element_bytes,swizzle):
    d=k._driver
    kind=getattr(d.CUtensorMapDataType,f'CU_TENSOR_MAP_DATA_TYPE_UINT{element_bytes*8}')
    mode=getattr(d.CUtensorMapSwizzle,f'CU_TENSOR_MAP_SWIZZLE_{swizzle}B')
    desc=sc._check(d.cuTensorMapEncodeTiled(kind,len(dims),value.data_ptr(),
        tuple(d.cuuint64_t(v) for v in dims),tuple(d.cuuint64_t(v) for v in strides),
        tuple(d.cuuint32_t(v) for v in box),tuple(d.cuuint32_t(1) for _ in box),
        d.CUtensorMapInterleave.CU_TENSOR_MAP_INTERLEAVE_NONE,mode,
        d.CUtensorMapL2promotion.CU_TENSOR_MAP_L2_PROMOTION_NONE,
        d.CUtensorMapFloatOOBfill.CU_TENSOR_MAP_FLOAT_OOB_FILL_NONE))
    storage=np.empty(191,dtype=np.uint8)
    aligned=storage[(-storage.ctypes.data)%64:][:128]
    aligned[:]=np.frombuffer(ctypes.string_at(desc.getPtr(),128),dtype=np.uint8)
    assert aligned.ctypes.data%64==0
    return aligned

def host_maps(k,weight,planes,rows,width,columns=32):
    return (encode_host(k,weight,(width,weight.shape[0]),(width*2,),(64,columns),element_bytes=2,swizzle=128),
            encode_host(k,planes,(width,rows,3),(width,width*rows),(64,32,1),element_bytes=1,swizzle=64))

def source(*args):
    s=pointer_source(*args)
    s='struct __align__(64) TensorMap128 { unsigned long long data[16]; };\n'+s
    s=once(s,'tma_stream(const qi_t* x,const u16* w,const void* wd,const void* ad,',
             'tma_stream(const qi_t* x,const u16* w,const __grid_constant__ TensorMap128 wd,const __grid_constant__ TensorMap128 ad,')
    return once(s,'tma_stream_body(x,w,wd,ad,bias,','tma_stream_body(x,w,&wd,&ad,bias,')

def launch(k,function,*,grid,block,arguments):
    storage=[a if isinstance(a,np.ndarray) else np.array([a.data_ptr()],dtype=np.uint64)
             if isinstance(a,torch.Tensor) else np.array([a],dtype=np.int32) for a in arguments]
    pointers=np.array([a.ctypes.data for a in storage],dtype=np.uint64)
    grid=(*grid,1,1)[:3]
    sc._check(k._driver.cuLaunchKernel(function,*grid,*block,1,0,torch.cuda.current_stream(k.device).cuda_stream,pointers.ctypes.data,0))

class TmaByValue(TmaMma):
    def __init__(self,width,columns=32,split=1,stages=2,min_blocks=0,has_bias=False):
        self.context=torch.empty(1,device='cuda');self.k=TmaOwner('cuda',magnitude_bits=22)
        assert self.k.arch=='sm_120' and width%16==0
        self.width,self.columns,self.split,self.has_bias=width,columns,split,has_bias
        self.name=f'tma-byvalue-v2-k{width}-n{columns}-s{split}-st{stages}-r{min_blocks}-b{int(has_bias)}'
        self.functions=self.k._compile(self.name,source(width,columns,split,stages,min_blocks,has_bias),['tma_stream','integer_finish'],integer_mma=True)
    def project(self,prepared,weight,ew,flag,bias=None,*,descriptors=None):
        planes,ex=prepared;rows=ex.numel();outputs=weight.shape[0]
        wd,ad=host_maps(self.k,weight,planes,rows,self.width,self.columns) if descriptors is None else descriptors
        self.last_maps=wd,ad
        out=torch.empty((rows,outputs),dtype=torch.float32,device=weight.device)
        partials=torch.empty((self.split,rows,outputs),dtype=torch.int64,device=weight.device) if self.split>1 else out
        b=weight if bias is None else bias
        launch(self.k,self.functions['tma_stream'],grid=(-(-outputs//self.columns),-(-rows//32),self.split),block=(128,1),
               arguments=(planes,weight,wd,ad,b,ex,ew,out,flag,partials,rows,outputs))
        if self.split>1:
            self.k._launch(self.functions['integer_finish'],grid=(-(-outputs//256),rows),block=(256,1),
                           pointers=(partials,b,ex,ew,out,flag),integers=(rows,outputs))
        return out
