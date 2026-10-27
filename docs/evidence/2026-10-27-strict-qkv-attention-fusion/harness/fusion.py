"""A GQA CTA finishes its own query heads and K/V cache slot before consuming them."""
import torch
from heteroes.eval import integer_cuda as ic,strict_cuda as sc

PREFIX=r'''
  const int columns=(heads+2*kv_heads)*dim,scale0=ex[i]-2*(MAGNITUDE_BITS-1),half=dim>>1;
  const float* cr=cosine+(size_t)i*dim;
  const float* sr=sine+(size_t)i*dim;
  if(x<half) {
    int n=h*dim+x;
    float lo=loaded(projected(partials,length,columns,i,n,scale0+eq[n],bq,n,error),bad);
    float hi=loaded(projected(partials,length,columns,i,n+half,scale0+eq[n+half],bq,n+half,error),bad);
    float first=add_(mul_(lo,load(cr+x,bad),bad),mul_(-hi,load(sr+x,bad),bad),bad);
    float second=add_(mul_(hi,load(cr+x+half,bad),bad),mul_(lo,load(sr+x+half,bad),bad),bad);
    query[r*padded+x+(x>>5)]=first;
    query[r*padded+x+half+((x+half)>>5)]=second;
  }
  const size_t position=((size_t)kv*total_keys+start+keys-1)*dim;
  if(r==0 && x<half) {
    int n=kv*dim+x,c=heads*dim+n;
    float lo=loaded(projected(partials,length,columns,i,c,scale0+ek[n],bk,n,error),bad);
    float hi=loaded(projected(partials,length,columns,i,c+half,scale0+ek[n+half],bk,n+half,error),bad);
    key[position+x]=add_(mul_(lo,load(cr+x,bad),bad),mul_(-hi,load(sr+x,bad),bad),bad);
    key[position+x+half]=add_(mul_(hi,load(cr+x+half,bad),bad),mul_(lo,load(sr+x+half,bad),bad),bad);
  }
  if(r==1) {
    int n=kv*dim+x,c=(heads+kv_heads)*dim+n;
    value[position+x]=projected(partials,length,columns,i,c,scale0+ev[n],bv,n,error);
  }
  // The following raw prefetch must observe this CTA's current K/V writes, including other warps.
  __syncthreads();
'''

def source(split,has_bias):
    start=sc._OPS_SOURCE.index('extern "C" __global__ void __launch_bounds__(512) strict_attention_gqa(')
    prefix,body=sc._OPS_SOURCE[:start],sc._OPS_SOURCE[start:]
    begin=body.index('  // Strided loops')
    body=r'''
extern "C" __global__ void __launch_bounds__(512) finish_qkv_attention(
  const i64* partials,const u16* bq,const u16* bk,const u16* bv,const int* ex,const int* eq,const int* ek,const int* ev,
  const float* cosine,const float* sine,float* key,float* value,float* out,int* error,const int* ranges,
  int heads,int length,int total_keys,int past,int repeats,int dim,int packed,int kv_heads,float scale) {
'''+body[begin:]
    old='  query[r * padded + x + (x >> 5)] = load(q + ((size_t)h * length + i) * dim + x, bad);'
    assert body.count(old)==1
    body=body.replace(old,PREFIX)
    header=''.join(f'#define {n} 0x{v:08x}u\n' for n,v in sc.reference_constants().items())
    header+=f'#define MAGNITUDE_BITS 22\n#define DIGITS 3\n#define SPLIT_K {split}\n#define HAS_BIAS {int(has_bias)}\n'
    return header+prefix+ic._DECODE_FINISH_SOURCE+body

class FusedKernels(ic.IntegerCudaKernels):
    @torch.inference_mode()
    def qkv_attention(self,prepared,weights,biases,cosine,sine,heads,kv_heads,ranges,keys,values,scale,*,max_keys,error_flag=None,decode_target_ctas_per_sm=None):
        dim=weights[0].shape[0]//heads;rows=prepared[1].numel();repeats=heads//kv_heads
        if not (self.arch=='sm_120' and self.magnitude_bits==22 and dim==64 and repeats>=2 and dim*repeats<=512):return None
        shared=4*((repeats+32)*(dim+dim//32)+2*repeats*max_keys)
        if shared>48*1024:return None
        flag=self.new_error_flag() if error_flag is None else error_flag
        raw=self._fused_group(None,weights,biases,prepared,flag,decode_target_ctas_per_sm)
        if raw is None:return None
        partials,ex,ew,plan=raw
        has_bias=biases is not None and biases[0] is not None
        bs=weights if not has_bias else biases
        name=f'qkv-attention-v1-s{plan.split_k}-b{int(has_bias)}'
        if name not in self._functions:
            self._functions[name]=self._compile(name,source(plan.split_k,has_bias),['finish_qkv_attention'],ptx_exact=sc.OPS_PTX_EXACT,sass_exact=sc.OPS_SASS_EXACT)['finish_qkv_attention']
        out=torch.empty((rows,heads*dim),device=self.device)
        self._launch(self._functions[name],grid=(rows,kv_heads),block=(dim,repeats),
                     pointers=(partials,*bs,ex,*ew,cosine,sine,keys,values,out,flag,ranges),
                     integers=(heads,rows,keys.shape[1],0,repeats,dim,1,kv_heads),floats=(scale,),shared=shared)
        self._finish(flag,error_flag)
        return out
