"""Unselected bounded per-projection B22 packing; never retains a model-sized integer shadow."""
from heteroes.eval import integer_cuda as ic
import torch

PACK_SOURCE = r'''
extern "C" __global__ void pack_prefill(const u16* w,const int* ew,unsigned* out,int rows) {
  int r=blockIdx.x, c=threadIdx.x;
  unsigned scale=(unsigned)((MAGNITUDE_BITS-1-ew[r])*0x800000);
  for(;c<WIDTH/4;c+=128) {
    uint2 h=*((const uint2*)w+(size_t)r*(WIDTH/4)+c);
    unsigned d[DIGITS];convert4(d,h.x,h.y,scale);
    #pragma unroll
    for(int i=0;i<DIGITS;++i)out[((size_t)i*rows+r)*(WIDTH/4)+c]=d[i];
  }
}
'''

def replace_once(source,old,new):
    assert source.count(old)==1,old[:120]
    return source.replace(old,new)

def source(width,columns):
    s=ic._SOURCE
    s=replace_once(s,'#define W_STAGE (NT*KS*2)','#define W_STAGE (DIGITS*NT*KS)')
    start=s.index('  // Weights: NT rows of eight sixteen-byte chunks')
    end=s.index('  // Activation planes:',start)
    s=s[:start]+r'''
  for(int c=tid;c<DIGITS*NT*4;c+=128) {
    int d=c/(NT*4), r=(c>>2)%NT, chunk=c&3, n=column0+r, k=k0+chunk*16;
    int valid=(n<outputs && k<WIDTH) ? 16 : 0;
    const unsigned char* source=(const unsigned char*)w+((size_t)d*outputs+n)*WIDTH+k;
    cp16(sw+(d*NT+r)*KS+((chunk^((r>>1)&3))<<4),valid ? (const void*)source : (const void*)w,valid);
  }
''' +s[end:]
    start=s.index('          int r=warp*8*JN+j*8+group;',s.index('void stream_body'))
    end=s.index('\n        }\n        #pragma unroll\n        for(int m=',start)
    s=s[:start]+r'''
          int r=warp*8*JN+j*8+group;
          #pragma unroll
          for(int d=0;d<DIGITS;++d) {
            const unsigned char* base=sw+(d*NT+r)*KS;
            int swizzle=(r>>1)&3;
            b[j][d][0]=*(const unsigned*)(base+(((step*2)^swizzle)<<4)+thread*4);
            b[j][d][1]=*(const unsigned*)(base+(((step*2+1)^swizzle)<<4)+thread*4);
          }
''' +s[end:]
    # Unused scale reads are optimized away. Raw halfs are only consumed by pack_prefill.
    defines={'WIDTH':width,'MAGNITUDE_BITS':22,'DIGITS':3,'HAS_BIAS':0,'M_GROUPS':2,
             'WARPS':4,'SPLIT_K':1,'PACKED_INPUT':1,'WEIGHT_READ32':0,'WEIGHT_PREFETCH':1,
             'FAST_CONVERT':1,'STREAM_LDSM_INPUT':1,'JN':columns//32,'STAGES':2,'STREAM_MIN_BLOCKS':3}
    return ''.join(f'#define {k} {v}\n' for k,v in defines.items())+s+PACK_SOURCE

class PackedPrefill:
    def __init__(self,kernels,width,columns=32):
        assert kernels.magnitude_bits==22 and width%64==0
        self.k,self.width,self.columns=kernels,width,columns
        self.functions=kernels._compile(f'bounded-prefill-pack-v1-k{width}-n{columns}',source(width,columns),
                                        ['pack_prefill','integer_stream'],integer_mma=True)
    def pack(self,weight,ew):
        scratch=torch.empty((3,*weight.shape),device=weight.device,dtype=torch.int8)
        self.last_scratch_bytes=scratch.numel()
        self.k._launch(self.functions['pack_prefill'],grid=(weight.shape[0],1),block=(128,1),
                       pointers=(weight,ew,scratch),integers=(weight.shape[0],))
        return scratch
    def project(self,prepared,packed,ew,out,flag):
        planes,ex=prepared
        rows,outputs=out.shape
        self.k._launch(self.functions['integer_stream'],grid=(-(-outputs//self.columns),-(-rows//32),1),
                       block=(128,1),pointers=(planes,packed,packed,ex,ew,out,flag,out),integers=(rows,outputs))
        return out
    def linear(self,value,weight):
        k=self.k
        flag=k.new_error_flag()
        ew=k._weight_exponents(weight,flag)
        prepared=k.quantize_input(value,error_flag=flag,_packed=True)
        packed=self.pack(weight,ew)
        out=torch.empty((value.shape[0],weight.shape[0]),dtype=torch.float32,device=value.device)
        self.project(prepared,packed,ew,out,flag)
        k._finish(flag,None)
        return out
