"""Guarded exact FP32 QK trees: operands on a common lattice make every intermediate normal or zero."""
from heteroes.eval.integer_cuda import IntegerCudaKernels

HELPERS=r'''
__device__ __forceinline__ bool score_safe(float v) {
  unsigned a=__float_as_uint(v)&0x7fffffffu;
  return a==0 || (a>=0x30800000u && a<=0x49800000u);
}
__device__ __forceinline__ float score_add(float a,float b,unsigned& bad) {
  float r;asm volatile("add.rn.f32 %0, %1, %2;" : "=f"(r) : "f"(a),"f"(b));return r;
}
__device__ __forceinline__ float score_mul(float a,float b,unsigned& bad) {
  float r;asm volatile("mul.rn.f32 %0, %1, %2;" : "=f"(r) : "f"(a),"f"(b));return r;
}
'''
def once(s,old,new):
    assert s.count(old)==1,(old,s.count(old))
    return s.replace(old,new)

def transform_gqa(s):
    start=s.index('extern "C" __global__ void __launch_bounds__(512) strict_attention_gqa(')
    # Fused quantization appends more entry points after the common operation source.
    depth=0;end=s.index('{',start)
    for end in range(end,len(s)):
        if s[end]=='{':depth+=1
        elif s[end]=='}':
            depth-=1
            if depth==0:break
    assert depth==0
    prefix,body,tail=s[:start],s[start:end+1],s[end+1:]
    body=once(body,'  unsigned bad = 0;','  __shared__ unsigned score_unsafe;\n  if(tid==0)score_unsafe=0;\n  unsigned bad = 0;')
    old='  query[r * padded + x + (x >> 5)] = load(q + ((size_t)h * length + i) * dim + x, bad);'
    body=once(body,old,old+'\n  unsigned unsafe=!score_safe(query[r*padded+x+(x>>5)]);')
    old='        note(target[3], bad);'
    body=once(body,old,old+'\n        unsafe|=!(score_safe(target[0])&&score_safe(target[1])&&score_safe(target[2])&&score_safe(target[3]));')
    body=once(body,'    stage(first);\n    __syncthreads();\n    if (first + 32 < keys) fetch(keys_base, first + 32);',
              '    stage(first);\n    if(unsafe)atomicOr(&score_unsafe,1u);\n    __syncthreads();\n    if (first + 32 < keys) fetch(keys_base, first + 32);')
    begin=body.index('    if (live) {');end=body.index('    if (live && lane == 0) numerators',begin)
    old=body[begin:end];raw=old.replace('mul_(','score_mul(').replace('add_(','score_add(')
    body=body[:begin]+'    if(score_unsafe==0) {\n'+raw+'    } else {\n'+old+'    }\n'+body[end:]
    return prefix+body+tail

def transform_prefill(s):
    start=s.index('// One warp per query/head slot;');prefix=s[:start];body=s[start:]
    body=once(body,'  unsigned bad = 0;', '  __shared__ unsigned score_unsafe;\n  if(threadIdx.x==0)score_unsafe=0;\n  __syncthreads();\n  unsigned unsafe=0;\n  unsigned bad = 0;')
    old='''  for (int d = lane; d < DIM; d += 32)
    query[r * padded + d + (d >> 5)] = live ? load(q + ((size_t)h * length + i) * DIM + d, bad) : 0.0f;'''
    body=once(body,old,'''  for (int d = lane; d < DIM; d += 32) {
    float v=live ? load(q + ((size_t)h * length + i) * DIM + d, bad) : 0.0f;
    query[r*padded+d+(d>>5)]=v;unsafe|=!score_safe(v);
  }''')
    old='      kv[row * padded + d + (d >> 5)] = load(base + ((size_t)blockIdx.y * total_keys + start) * DIM + index, bad);'
    body=once(body,old,'''      float v=load(base+((size_t)blockIdx.y*total_keys+start)*DIM+index,bad);
      kv[row*padded+d+(d>>5)]=v;if(base==key)unsafe|=!score_safe(v);''')
    body=once(body,'  stage(key);\n  __syncthreads();','  stage(key);\n  if(unsafe)atomicOr(&score_unsafe,1u);\n  __syncthreads();')
    begin=body.index('  if (live) {');end=body.index('  __syncthreads();\n  stage(value);',begin)
    old=body[begin:end];raw=old.replace('mul_(','score_mul(').replace('add_(','score_add(')
    raw=once(raw,'score_mul(v,scale,bad)','mul_(v,scale,bad)')
    body=body[:begin]+'  if(score_unsafe==0) {\n'+raw+'  } else {\n'+old+'  }\n'+body[end:]
    return prefix+body

class BoundedAttentionKernels(IntegerCudaKernels):
    def _compile(self,name,source,entries,**kwargs):
        changed=False
        if 'strict_attention_gqa(' in source:source=transform_gqa(source);changed=True
        if '// One warp per query/head slot;' in source:source=transform_prefill(source);changed=True
        if changed:source=HELPERS+source;name='bounded-score-v1-'+name
        return super()._compile(name,source,entries,**kwargs)
