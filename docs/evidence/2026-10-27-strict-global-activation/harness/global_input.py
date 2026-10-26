"""Unselected dataflow change: stage only FP16 weights; canonical activation bytes load from global/L1."""
import torch
from heteroes.eval import integer_cuda as ic

def source(width,columns,split,min_blocks):
    s=ic._SOURCE
    start=s.index('  // Activation planes: DIGITS*MT rows')
    end=s.index('\n#if FAST_CONVERT',start)
    s=s[:start]+'}\n'+s[end:]
    assert s.count('unsigned char inputs_shared[STAGES][A_STAGE];')==1
    s=s.replace('unsigned char inputs_shared[STAGES][A_STAGE];','unsigned char inputs_shared[STAGES][1];')
    start=s.index('#if STREAM_LDSM_INPUT\n          // Four m8/k16 byte quadrants')
    end=s.index('#endif',start)+len('#endif')
    s=s[:start]+r'''
          int row=first+m*16+group,word=(begin+it)*16+step*8+thread;
          #pragma unroll
          for(int d=0;d<DIGITS;++d) {
            const unsigned* plane=(const unsigned*)x+(size_t)d*rows*(WIDTH/4);
            a[d][0]=(row<rows && word<WIDTH/4) ? plane[(size_t)row*(WIDTH/4)+word] : 0;
            a[d][1]=(row+8<rows && word<WIDTH/4) ? plane[(size_t)(row+8)*(WIDTH/4)+word] : 0;
            a[d][2]=(row<rows && word+4<WIDTH/4) ? plane[(size_t)row*(WIDTH/4)+word+4] : 0;
            a[d][3]=(row+8<rows && word+4<WIDTH/4) ? plane[(size_t)(row+8)*(WIDTH/4)+word+4] : 0;
          }
''' +s[end:]
    defines={'WIDTH':width,'MAGNITUDE_BITS':22,'DIGITS':3,'HAS_BIAS':0,'M_GROUPS':2,'WARPS':4,
             'SPLIT_K':split,'PACKED_INPUT':1,'WEIGHT_READ32':0,'WEIGHT_PREFETCH':1,'FAST_CONVERT':1,
             'STREAM_LDSM_INPUT':1,'JN':columns//32,'STAGES':2 if columns==64 else 3,'STREAM_MIN_BLOCKS':min_blocks}
    return ''.join(f'#define {key} {value}\n' for key,value in defines.items())+s

class GlobalInput:
    def __init__(self,kernels,width,columns,split,min_blocks=0):
        assert kernels.magnitude_bits==22 and width%16==0
        self.k,self.width,self.columns,self.split=kernels,width,columns,split
        self.name=f'global-input-v1-k{width}-n{columns}-s{split}-r{min_blocks}'
        self.functions=kernels._compile(self.name,source(width,columns,split,min_blocks),['integer_stream','integer_finish'],integer_mma=True)
    def project(self,prepared,weight,ew,flag):
        planes,ex=prepared;rows=ex.numel();outputs=weight.shape[0]
        out=torch.empty((rows,outputs),dtype=torch.float32,device=weight.device)
        partials=torch.empty((self.split,rows,outputs),dtype=torch.int64,device=weight.device) if self.split>1 else out
        self.k._launch(self.functions['integer_stream'],grid=(-(-outputs//self.columns),-(-rows//32),self.split),block=(128,1),
                       pointers=(planes,weight,weight,ex,ew,out,flag,partials),integers=(rows,outputs))
        if self.split>1:
            self.k._launch(self.functions['integer_finish'],grid=(-(-outputs//256),rows),block=(256,1),
                           pointers=(partials,weight,ex,ew,out,flag),integers=(rows,outputs))
        return out
