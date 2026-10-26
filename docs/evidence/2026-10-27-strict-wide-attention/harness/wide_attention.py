"""Unselected short-context GQA: four score lanes, two 32-key value workers, same pruned FP32 tree."""
import torch
from heteroes.eval import strict_cuda as sc

def once(s,old,new):
    assert s.count(old)==1,old
    return s.replace(old,new)

def source():
    s=sc._OPS_SOURCE[sc._OPS_SOURCE.index('extern "C" __global__ void __launch_bounds__(512) strict_attention_gqa'):]
    s=s.replace('__launch_bounds__(512) strict_attention_gqa','__launch_bounds__(896) strict_attention_gqa_wide',1)
    s=once(s,'const int tid = r * dim + x, threads = repeats * dim, h = kv * repeats + r;',
           'const int tid = r * 2 * dim + x, threads = repeats * 2 * dim, h = kv * repeats + r;\n  int tile_rows=32;')
    s=once(s,'const int lane_shift = dim_shift - 5','const int lane_shift = dim_shift - 4')
    s=once(s,'const int padded = dim + lanes;','const int padded = dim + (dim >> 5);')
    s=once(s,'float* numerators = tile + 32 * padded;','float* numerators = tile + 64 * padded;')
    s=once(s,'float* tree = numerators + repeats * keys;', 'float* tree = numerators + repeats * keys;\n  float* roots = tree + repeats * keys;')
    s=once(s,'query[r * padded + x + (x >> 5)] = load(', 'if(x<dim) query[r * padded + x + (x >> 5)] = load(')
    before,after=s.split('  // Score lanes:',1)
    assert before.count('keys - first < 32 ? keys - first : 32')==2
    before=before.replace('keys - first < 32 ? keys - first : 32','keys - first < tile_rows ? keys - first : tile_rows')
    s=before+'  // Score lanes:'+after
    s=once(s,'query + score_head * padded + lane * 33','query + score_head * padded + lane * 16 + (lane >> 1)')
    s=once(s,'tile + score_row * padded + lane * 33','tile + score_row * padded + lane * 16 + (lane >> 1)')
    before,after=s.split('  fetch(values_base, 0);',1)
    before=before.replace('float group[4];','float group[2];').replace('g < 4;','g < 2;')
    before=once(before,'v = add_(add_(group[0], group[1], bad), add_(group[2], group[3], bad), bad);','v = add_(group[0], group[1], bad);')
    s=before+'  tile_rows=64;\n  fetch(values_base, 0);'+after
    s=once(s,'for (int w = (r * dim) >> 5; w < ((r + 1) * dim) >> 5; ++w)',
           'for (int w = (r * 2 * dim) >> 5; w < ((r + 1) * 2 * dim) >> 5; ++w)')
    start=s.index('  const int channel = x + (x >> 5);')
    end=s.index('  report(error, bad);',start)
    s=s[:start]+r'''
  const int worker=x>>6,channel=x&63,padded_channel=channel+(channel>>5);
  float pair0=0.0f,pair1=0.0f;
#pragma unroll
  for(int segment=0;segment<2;++segment) {
    int first=segment*64;
    if(first<keys) {
      int rows=keys-first<64 ? keys-first : 64;
      __syncthreads();stage(first);__syncthreads();
      if(first+64<keys) fetch(values_base,first+64);
      int valid_rows=rows-worker*32;
      if(valid_rows>32) valid_rows=32;
      float group[4]={};
#pragma unroll
      for(int g=0;g<4;++g) {
        int base=8*g,valid=valid_rows-base<8 ? valid_rows-base : 8;
        float terms[8]={};
#pragma unroll
        for(int item=0;item<8;++item)
          if(item<valid) terms[item]=mul_(scores[first+worker*32+base+item],tile[(worker*32+base+item)*padded+padded_channel],bad);
#pragma unroll
        for(int stride=1;stride<8;stride<<=1) {
#pragma unroll
          for(int item=0;item<8;item+=2*stride)
            if(item+stride<valid) terms[item]=add_(terms[item],terms[item+stride],bad);
        }
        group[g]=terms[0];
      }
      int present=valid_rows>0 ? (valid_rows+7)>>3 : 0;
      if(1<present) group[0]=add_(group[0],group[1],bad);
      if(3<present) group[2]=add_(group[2],group[3],bad);
      if(2<present) group[0]=add_(group[0],group[2],bad);
      roots[r*128+channel*2+worker]=group[0];
      __syncthreads();
      if(worker==0) {
        float root=roots[r*128+channel*2];
        if(rows>32) root=add_(root,roots[r*128+channel*2+1],bad);
        if(segment==0) pair0=root;else pair1=root;
      }
    }
  }
  if(worker==0) out[(size_t)i*heads*dim+h*dim+channel]=keys>64 ? add_(pair0,pair1,bad) : pair0;
''' +s[end:]
    return s

class WideAttention:
    def __init__(self):
        self.owner=sc.StrictCudaKernels('cuda')
        header=''.join(f'#define {k} 0x{v:08x}u\n' for k,v in sc.reference_constants().items())
        self.fn=self.owner._compile('wide-gqa-64-7-k128',header+sc._OPS_SOURCE+source(),['strict_attention_gqa_wide'],ptx_exact=sc.OPS_PTX_EXACT,sass_exact=sc.OPS_SASS_EXACT)['strict_attention_gqa_wide']
    def run(self,q,key,value,layout,flag):
        assert q.shape[0]==14 and q.shape[2]==64 and key.shape[0]==2 and layout.max_keys<=128
        result=torch.empty((q.shape[1],14*64),dtype=torch.float32,device=q.device)
        shared=4*(7*66+64*66+2*7*layout.max_keys+7*128)
        self.owner._launch(self.fn,grid=(q.shape[1],2),block=(128,7),pointers=(q,key,value,result,flag,layout.ranges),
                           integers=(14,q.shape[1],key.shape[1],0,7,64,1),floats=(.125,),shared=shared)
        return result
