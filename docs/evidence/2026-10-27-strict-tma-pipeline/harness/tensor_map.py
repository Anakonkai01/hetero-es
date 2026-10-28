"""Typed CUDA tensor map construction; maps addresses/layouts, never a copy of weight values."""
import ctypes
import numpy as np
import torch
from heteroes.eval import strict_cuda as sc

def encode(k,value,dims,strides,box,*,element_bytes,swizzle):
    d=k._driver
    kind=d.CUtensorMapDataType.CU_TENSOR_MAP_DATA_TYPE_UINT16 if element_bytes==2 else d.CUtensorMapDataType.CU_TENSOR_MAP_DATA_TYPE_UINT8
    mode={0:d.CUtensorMapSwizzle.CU_TENSOR_MAP_SWIZZLE_NONE,64:d.CUtensorMapSwizzle.CU_TENSOR_MAP_SWIZZLE_64B,128:d.CUtensorMapSwizzle.CU_TENSOR_MAP_SWIZZLE_128B}[swizzle]
    descriptor=sc._check(d.cuTensorMapEncodeTiled(kind,len(dims),value.data_ptr(),
        tuple(d.cuuint64_t(v) for v in dims),tuple(d.cuuint64_t(v) for v in strides),
        tuple(d.cuuint32_t(v) for v in box),tuple(d.cuuint32_t(1) for _ in box),
        d.CUtensorMapInterleave.CU_TENSOR_MAP_INTERLEAVE_NONE,mode,
        d.CUtensorMapL2promotion.CU_TENSOR_MAP_L2_PROMOTION_NONE,
        d.CUtensorMapFloatOOBfill.CU_TENSOR_MAP_FLOAT_OOB_FILL_NONE))
    raw=ctypes.string_at(descriptor.getPtr(),128)
    result=torch.from_numpy(np.frombuffer(raw,dtype=np.uint8).copy()).to(value.device)
    assert result.data_ptr()%64==0
    return result

def maps(k,weight,planes,rows,width,columns=32,row_tile=32):
    w=encode(k,weight,(width,weight.shape[0]),(width*2,),(64,columns),element_bytes=2,swizzle=128)
    a=encode(k,planes,(width,rows,3),(width,width*rows),(64,row_tile,1),element_bytes=1,swizzle=64)
    return w,a
