"""Unselected reciprocal lookup microkernel; explicit table operands, no hidden global pointer."""
import hashlib
import torch
from heteroes.eval import strict_cuda as sc
from lookup import build_table
from compressed import compress

SOURCE=r'''
__device__ __forceinline__ float reciprocal_lookup(float x,const unsigned* anchors,const unsigned char* packed,unsigned& bad) {
  // Outside the declared finite positive domain, execute every original flag/NaN operation.
  if (!(x>=k(DOMAIN_LOW) && x<=k(DOMAIN_HIGH))) return reciprocal_(x,bad);
  unsigned u=__float_as_uint(x), m=u&0x7fffffu, index=m>>11, low=m&2047u;
  int start=(int)anchors[index], delta=(int)anchors[index+1]-start;
  int chord=start+((delta*(int)low)>>11);
  int correction=((packed[m>>1]>>((m&1u)*4u))&15)-8;
  int exponent=(int)(u>>23)-127;
  unsigned result=(unsigned)(chord+correction)-(unsigned)(exponent*0x800000);
  return __uint_as_float(result);
}
extern "C" __global__ void compare_reciprocal(const float* values,const unsigned* anchors,const unsigned char* packed,int* out,int count) {
  int i=blockIdx.x*256+threadIdx.x;
  if(i<count) {
    unsigned old_bad=0,new_bad=0;
    float x=load(values+i,old_bad),y=load(values+i,new_bad);
    out[(size_t)i*4]=__float_as_int(reciprocal_(x,old_bad));
    out[(size_t)i*4+1]=__float_as_int(reciprocal_lookup(y,anchors,packed,new_bad));
    out[(size_t)i*4+2]=old_bad;out[(size_t)i*4+3]=new_bad;
  }
}
extern "C" __global__ void lookup_silu_mul(const float* gate,const float* up,const unsigned* anchors,const unsigned char* packed,float* out,int* error,int count) {
  unsigned bad=0;
  int i=blockIdx.x*256+threadIdx.x;
  if(i<count) {
    float x=load(gate+i,bad);
    float small=exp_(-fabsf(x),bad);
    float denominator=reciprocal_lookup(add_(1.0f,small,bad),anchors,packed,bad);
    float positive=mul_(x,denominator,bad);
    float negative=mul_(mul_(x,small,bad),denominator,bad);
    float silu=x>=0.0f ? positive : negative;
    out[i]=mul_(silu,load(up+i,bad),bad);
  }
  report(error,bad);
}
'''

class LookupKernels:
    def __init__(self):
        self.owner=sc.StrictCudaKernels('cuda')
        table=build_table();anchors,packed=compress(table)
        self.table_sha256=hashlib.sha256(table.tobytes()).hexdigest()
        self.anchors=torch.from_numpy(anchors).cuda();self.packed=torch.from_numpy(packed).cuda()
        self.table_bytes=anchors.nbytes+packed.nbytes
        header=''.join(f'#define {k} 0x{v:08x}u\n' for k,v in sc.reference_constants().items())
        self.functions=self.owner._compile('exact-reciprocal-nibble-v1',header+sc._OPS_SOURCE+SOURCE,
                    ['compare_reciprocal','lookup_silu_mul'],ptx_exact=sc.OPS_PTX_EXACT,sass_exact=sc.OPS_SASS_EXACT)
    def compare(self,values):
        result=torch.empty((values.numel(),4),dtype=torch.int32,device='cuda')
        self.owner._launch(self.functions['compare_reciprocal'],grid=-(-values.numel()//256),block=(256,1),
                           pointers=(values,self.anchors,self.packed,result),integers=(values.numel(),))
        return result
    def silu_mul(self,gate,up,*,error_flag=None):
        assert gate.shape==up.shape and gate.is_contiguous() and up.is_contiguous()
        result=torch.empty_like(gate);flag=self.owner.new_error_flag() if error_flag is None else error_flag
        self.owner._launch(self.functions['lookup_silu_mul'],grid=-(-gate.numel()//256),block=(256,1),
                           pointers=(gate,up,self.anchors,self.packed,result,flag),integers=(gate.numel(),))
        self.owner._finish(flag,error_flag)
        return result
