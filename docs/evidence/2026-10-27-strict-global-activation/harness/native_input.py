"""Unselected native activation fragments: one coalesced uint4 global/L1 load per digit and m16/k32 tile.

The temporary packing launch is measured separately. A selected implementation would have to publish this
layout directly from the already existing quantization producers to avoid an extra decode launch.
"""
import torch
from global_input import GlobalInput,source as global_source

PACK=r'''
extern "C" __global__ void pack_native(const unsigned* input,unsigned* out,int rows) {
  int t=threadIdx.x,lane=t>>2,reg=t&3;
  int mt=blockIdx.y,kt=blockIdx.x,d=blockIdx.z;
  int row=mt*16+(lane>>2)+(reg&1)*8,word=kt*8+(lane&3)+(reg>>1)*4;
  int mtiles=(rows+15)/16;
  const int ktiles=(WIDTH+31)/32;
  size_t dest=(((size_t)d*mtiles+mt)*ktiles+kt)*128+t;
  out[dest]=(row<rows && word<WIDTH/4) ? input[((size_t)d*rows+row)*(WIDTH/4)+word] : 0;
}
'''

def source(width,columns,split,min_blocks):
    s=global_source(width,columns,split,min_blocks)
    start=s.index('          int row=first+m*16+group,word=')
    end=s.index('          #pragma unroll\n          for(int i=0;i<DIGITS',start)
    s=s[:start]+r'''
          const int ktile=(begin+it)*2+step,ktiles=(WIDTH+31)/32;
          int mtile=(first>>4)+m,mtiles=(rows+15)/16;
          #pragma unroll
          for(int d=0;d<DIGITS;++d) {
            uint4 fragment={0,0,0,0};
            if(mtile<mtiles && ktile<ktiles) {
              const unsigned* p=(const unsigned*)x+((((size_t)d*mtiles+mtile)*ktiles+ktile)*32+lane)*4;
              fragment=*(const uint4*)p;
            }
            a[d][0]=fragment.x;a[d][1]=fragment.y;a[d][2]=fragment.z;a[d][3]=fragment.w;
          }
''' +s[end:]
    return s+PACK

class NativeInput(GlobalInput):
    def __init__(self,kernels,width,columns,split,min_blocks=0):
        assert kernels.magnitude_bits==22 and width%16==0
        self.k,self.width,self.columns,self.split=kernels,width,columns,split
        self.name=f'native-input-v1-k{width}-n{columns}-s{split}-r{min_blocks}'
        self.functions=kernels._compile(self.name,source(width,columns,split,min_blocks),['integer_stream','integer_finish','pack_native'],integer_mma=True)
    def pack(self,prepared):
        planes,ex=prepared;rows=ex.numel();mtiles=(rows+15)//16;ktiles=(self.width+31)//32
        out=torch.empty(3*mtiles*ktiles*128,dtype=torch.int32,device=planes.device)
        self.k._launch(self.functions['pack_native'],grid=(ktiles,mtiles,3),block=(128,1),pointers=(planes,out),integers=(rows,))
        return out,ex
    def project(self,prepared,weight,ew,flag,*,native=False):
        return super().project(prepared if native else self.pack(prepared),weight,ew,flag)
