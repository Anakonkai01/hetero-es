"""V2: additionally specialize the original exp polynomial inside its bounded normal domain."""
from heteroes.eval.integer_cuda import IntegerCudaKernels
from normal import transform as transform_reciprocal

EXP=r'''
__device__ float exp_(float x,unsigned& bad) {
  if(!(x>=-80.0f && x<=80.0f))return original_exp_(x,bad);
  if(fabsf(x)<=0x1p-26f)return 1.0f;
  int power=(int)floorf(normal_add(normal_mul(x,k(LOG2E)),0.5f));
  float exponent=(float)power;
  float remainder=normal_add(x,-normal_mul(exponent,k(LN2_HI)));
  remainder=normal_add(remainder,-normal_mul(exponent,k(LN2_LO)));
  float p=k(EXP_C0);
  p=normal_add(normal_mul(p,remainder),k(EXP_C1));
  p=normal_add(normal_mul(p,remainder),k(EXP_C2));
  p=normal_add(normal_mul(p,remainder),k(EXP_C3));
  p=normal_add(normal_mul(p,remainder),k(EXP_C4));
  p=normal_add(normal_mul(p,remainder),k(EXP_C5));
  p=normal_add(normal_mul(p,remainder),k(EXP_C6));
  p=normal_add(normal_mul(p,remainder),k(EXP_C7));
  p=normal_add(normal_mul(p,remainder),k(EXP_C8));
  return normal_mul(p,__int_as_float((power+127)<<23));
}
'''
def transform(source):
    source=transform_reciprocal(source)
    start=source.index('__device__ float exp_(');stop=source.index('__device__ float silu_(',start)
    old=source[start:stop]
    return source[:start]+old.replace('float exp_(','float original_exp_(',1)+EXP+source[stop:]

class NormalExpKernels(IntegerCudaKernels):
    def _compile(self,name,source,entries,**kwargs):
        if '__device__ float reciprocal_(' in source:
            source=transform(source);name='normal-v2-'+name
        return super()._compile(name,source,entries,**kwargs)
