"""Scratch only: reduce aligned key chunks within warps and reuse the dead maximum plane for warp roots."""
from heteroes.eval import strict_cuda as sc

DENOM = r'''
  int chunk_shift = 0;
  while (((1 << chunk_shift) * dim) < keys) ++chunk_shift;
  const int chunk = 1 << chunk_shift, root_count = (keys + chunk - 1) >> chunk_shift;
  const int begin = x * chunk, end = begin + chunk < keys ? begin + chunk : keys;
  GqaTree denominator_tree; denominator_tree.n = 0;
  for (int first = begin; first < end; first += 8) {
    const int valid = end - first < 8 ? end - first : 8;
    float terms[8] = {};
#pragma unroll
    for (int b = 0; b < 8; ++b) if (b < valid) terms[b] = own_tree[first + b];
#pragma unroll
    for (int s = 1; s < 8; s <<= 1) {
#pragma unroll
      for (int b = 0; b < 8; b += 2 * s) if (b + s < valid) terms[b] = add_(terms[b], terms[b+s], bad);
    }
    gqa_push(denominator_tree, terms[0], bad);
  }
  float root = gqa_finish(denominator_tree, bad);
#pragma unroll
  for (int s = 1; s < 32; s <<= 1) {
    float other = __shfl_down_sync(0xffffffffu, root, s);
    if ((x & (2*s-1)) == 0 && x + s < root_count) root = add_(root, other, bad);
  }
  if ((x & 31) == 0) maxima[tid >> 5] = root;
  __syncthreads();
  const int root_warps = (root_count + 31) >> 5;
  float warp_roots[8] = {};
#pragma unroll
  for (int w = 0; w < 8; ++w) if (w < root_warps) warp_roots[w] = maxima[((r * dim) >> 5) + w];
#pragma unroll
  for (int s = 1; s < 8; s <<= 1) {
#pragma unroll
    for (int w = 0; w < 8; w += 2 * s) if (w + s < root_warps)
      warp_roots[w] = add_(warp_roots[w], warp_roots[w+s], bad);
  }
  float denominator = warp_roots[0];
'''

def source(code):
    marker='extern "C" __global__ void __launch_bounds__(512) strict_attention_gqa'
    assert code.count(marker)==1
    before,after=code.split(marker)
    helpers=code[code.index('struct Tree {'):code.index('// In-place aligned tree')]
    helpers=helpers.replace('Tree','GqaTree').replace('[17]','[8]').replace('level < 17','level < 8')
    helpers=helpers.replace('void push(', 'void gqa_push(').replace('float finish(', 'float gqa_finish(')
    after=after.replace('Tree t;','GqaTree t;').replace('push(t,','gqa_push(t,').replace('finish(t,','gqa_finish(t,')
    first=after.index('  // block_tree for every head at once:')
    last=after.index('  float inverse = reciprocal_',first)
    after=after[:first]+DENOM+after[last:]
    return before+helpers+marker+after

def install(kernels):
    original=kernels._compile
    def compile_(name,code,entries,**kw):
        if name=='ops':code=source(code)
        return original(name,code,entries,**kw)
    kernels._compile=compile_
