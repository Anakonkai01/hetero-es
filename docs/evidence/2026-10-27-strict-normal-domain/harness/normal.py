"""Proof-directed prototype: remove redundant node flush/checks only inside the admitted normal domain."""
from heteroes.eval import strict_cuda as sc
from heteroes.eval.integer_cuda import IntegerCudaKernels

RAW=r'''
__device__ __forceinline__ float normal_add(float a,float b) {
  float r;asm volatile("add.rn.f32 %0, %1, %2;" : "=f"(r) : "f"(a),"f"(b));return r;
}
__device__ __forceinline__ float normal_mul(float a,float b) {
  float r;asm volatile("mul.rn.f32 %0, %1, %2;" : "=f"(r) : "f"(a),"f"(b));return r;
}
'''
RECIP=r'''
__device__ float reciprocal_(float x,unsigned& bad) {
  if(!(x>=k(DOMAIN_LOW) && x<=k(DOMAIN_HIGH)))return original_reciprocal_(x,bad);
  float r=__int_as_float(0x7EF311C3-__float_as_int(x));
  #pragma unroll
  for(int i=0;i<5;++i)r=normal_mul(r,normal_add(2.0f,-normal_mul(x,r)));
  return r;
}
'''
RSQRT=r'''
__device__ float rsqrt_(float x,unsigned& bad) {
  if(!(x>=k(DOMAIN_LOW) && x<=k(DOMAIN_HIGH)))return original_rsqrt_(x,bad);
  float r=__int_as_float(0x5F3759DF-(__float_as_int(x)>>1));
  #pragma unroll
  for(int i=0;i<6;++i) {
    float square=normal_mul(r,r);
    r=normal_mul(normal_mul(0.5f,r),normal_add(3.0f,-normal_mul(x,square)));
  }
  return r;
}
'''

def transform(source):
    for name,end,replacement in (('reciprocal_','rsqrt_',RECIP),('rsqrt_','exp_',RSQRT)):
        start=source.index(f'__device__ float {name}(')
        stop=source.index(f'__device__ float {end}(',start)
        old=source[start:stop]
        source=source[:start]+old.replace(f'float {name}(',f'float original_{name}(',1)+replacement+source[stop:]
    return RAW+source

class NormalKernels(IntegerCudaKernels):
    def _compile(self,name,source,entries,**kwargs):
        if '__device__ float reciprocal_(' in source:
            source=transform(source)
            name='normal-v1-'+name
        return super()._compile(name,source,entries,**kwargs)
