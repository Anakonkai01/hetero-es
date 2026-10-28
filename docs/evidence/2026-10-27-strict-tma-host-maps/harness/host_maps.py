"""Bounded CPU tensor-map templates; patch only their addresses through the CUDA API before each launch."""
from collections import OrderedDict
import ctypes
import numpy as np
from heteroes.eval import strict_cuda as sc

class HostMapCache:
    def __init__(self,k,capacity=16):
        self.driver=k._driver;self.capacity=capacity;self.entries=OrderedDict()
        self.encoded=0;self.patched=0
    def get(self,value,dims,strides,box,element_bytes,swizzle):
        d=self.driver;key=(dims,strides,box,element_bytes,swizzle)
        entry=self.entries.pop(key,None)
        if entry is None:
            kind=getattr(d.CUtensorMapDataType,f'CU_TENSOR_MAP_DATA_TYPE_UINT{element_bytes*8}')
            mode=getattr(d.CUtensorMapSwizzle,f'CU_TENSOR_MAP_SWIZZLE_{swizzle}B')
            desc=sc._check(d.cuTensorMapEncodeTiled(kind,len(dims),value.data_ptr(),
                tuple(d.cuuint64_t(v) for v in dims),tuple(d.cuuint64_t(v) for v in strides),
                tuple(d.cuuint32_t(v) for v in box),tuple(d.cuuint32_t(1) for _ in box),
                d.CUtensorMapInterleave.CU_TENSOR_MAP_INTERLEAVE_NONE,mode,
                d.CUtensorMapL2promotion.CU_TENSOR_MAP_L2_PROMOTION_NONE,
                d.CUtensorMapFloatOOBfill.CU_TENSOR_MAP_FLOAT_OOB_FILL_NONE))
            raw=np.empty(191,dtype=np.uint8);buffer=raw[(-raw.ctypes.data)%64:][:128]
            entry=desc,buffer;self.encoded+=1
        else:
            sc._check(d.cuTensorMapReplaceAddress(entry[0],value.data_ptr()));self.patched+=1
        self.entries[key]=entry
        while len(self.entries)>self.capacity:self.entries.popitem(last=False)
        desc,buffer=entry
        buffer[:]=np.frombuffer(ctypes.string_at(desc.getPtr(),128),dtype=np.uint8)
        return buffer
    def maps(self,weight,planes,rows,width,columns):
        w=self.get(weight,(width,weight.shape[0]),(width*2,),(64,columns),2,128)
        a=self.get(planes,(width,rows,3),(width,width*rows),(64,32,1),1,64)
        return w,a
