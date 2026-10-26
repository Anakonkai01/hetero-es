// Scratch prototype: one warp per query, QTILE consecutive queries of one sequence/head per CTA.
// All K rows are staged, then that plane is reused for V. No masked key or value load is omitted.
struct PrefillTree { float s[4]; unsigned n; };
__device__ __forceinline__ void prefill_push(PrefillTree& t, float v, unsigned& bad) {
  unsigned i=t.n++;
#pragma unroll
  for (int level=0; level<4; ++level) {
    if ((i>>level)&1u) v=add_(t.s[level],v,bad);
    else { t.s[level]=v; return; }
  }
}
__device__ __forceinline__ float prefill_finish(const PrefillTree& t, unsigned& bad) {
  float acc=0.0f; bool any=false;
#pragma unroll
  for (int level=0; level<4; ++level) if ((t.n>>level)&1u) {
    acc=any ? add_(t.s[level],acc,bad) : t.s[level]; any=true;
  }
  return acc;
}
extern "C" __global__ void __launch_bounds__(QTILE * 32) strict_attention_prefill(
    const float* q, const float* key, const float* value, float* out, int* error,
    const int* tiles, int heads, int length, int total_keys, int repeats, float scale) {
  const int lane = threadIdx.x & 31, r = threadIdx.x >> 5;
  const int* range = tiles + 5 * blockIdx.x;
  const int qr=r/HEAD_TILE, rh=r%HEAD_TILE;
  const int first_query = range[0], count = range[1], start = range[2], keys = range[3], limit = range[4] + qr;
  const int local_head=blockIdx.z*HEAD_TILE+rh;
  const bool live=qr<count && local_head<repeats;
  const int h = blockIdx.y * repeats + local_head, i = first_query + qr;
  constexpr int lanes = DIM / 32, padded = DIM + lanes;
  extern __shared__ float shared[];
  float* query = shared;
  float* kv = query + QTILE * padded;
  float* scores = kv + keys * padded;
  unsigned bad = 0;
#pragma unroll
  for (int d = lane; d < DIM; d += 32)
    query[r * padded + d + (d >> 5)] = live ? load(q + ((size_t)h * length + i) * DIM + d, bad) : 0.0f;
  auto stage = [&](const float* base) {
    for (int index = threadIdx.x; index < keys * DIM; index += QTILE * 32) {
      const int row = index / DIM, d = index % DIM;
      kv[row * padded + d + (d >> 5)] = load(base + ((size_t)blockIdx.y * total_keys + start) * DIM + index, bad);
    }
  };
  stage(key);
  __syncthreads();
  if (live) {
    const int g = lane & (lanes - 1), row_lane = lane / lanes;
    const float* own = query + r * padded + g * 33;
    for (int first = 0; first < keys; first += 32 / lanes) {
      const int j = first + row_lane;
      float v = 0.0f;
      if (j < keys) {
        const float* row = kv + j * padded + g * 33;
        float group[4];
#pragma unroll
        for (int a = 0; a < 4; ++a) {
          float terms[8];
#pragma unroll
          for (int b = 0; b < 8; ++b) terms[b] = mul_(own[8*a+b], row[8*a+b], bad);
#pragma unroll
          for (int s = 1; s < 8; s <<= 1) {
#pragma unroll
            for (int b = 0; b < 8; b += 2*s) terms[b] = add_(terms[b], terms[b+s], bad);
          }
          group[a] = terms[0];
        }
        v = add_(add_(group[0],group[1],bad),add_(group[2],group[3],bad),bad);
      }
#pragma unroll
      for (int s = 1; s < lanes; s <<= 1) {
        float other = __shfl_down_sync(0xffffffffu, v, s, lanes);
        if (j < keys && (g & (2*s-1)) == 0) v = add_(v,other,bad);
      }
      if (j < keys && g == 0) scores[r*keys+j] = mul_(v,scale,bad);
    }
  }
  __syncthreads();
  stage(value);
  __syncthreads();
  if (live) {
    float* own = scores + r * keys;
    float local = -FLT_BIG;
    for (int j = lane; j < keys; j += 32) if (j <= limit && own[j] > local) local = own[j];
#pragma unroll
    for (int s = 16; s > 0; s >>= 1) {
      float other = __shfl_xor_sync(0xffffffffu, local, s);
      local = other > local ? other : local;
    }
    if (__float_as_uint(local) == 0x80000000u) local = 0.0f;
    for (int j = lane; j < keys; j += 32) {
      bool allowed = j <= limit;
      float e = exp_(add_(allowed ? own[j] : local, -local, bad), bad);
      own[j] = allowed ? e : 0.0f;
    }
    __syncwarp();
    const int groups = (keys + 7) >> 3, valid = keys - 8*lane < 8 ? keys - 8*lane : 8;
    float terms[8] = {};
#pragma unroll
    for (int b = 0; b < 8; ++b) if (b < valid) terms[b] = own[8*lane+b];
#pragma unroll
    for (int s = 1; s < 8; s <<= 1) {
#pragma unroll
      for (int b = 0; b < 8; b += 2*s) if (b+s < valid) terms[b] = add_(terms[b],terms[b+s],bad);
    }
    float denominator = terms[0];
#pragma unroll
    for (int s = 1; s < 32; s <<= 1) {
      float other = __shfl_down_sync(0xffffffffu, denominator, s);
      if ((lane & (2*s-1)) == 0 && lane+s < groups) denominator = add_(denominator,other,bad);
    }
    float inverse = 0.0f;
    if (lane == 0) inverse = reciprocal_(denominator == 0.0f ? 1.0f : denominator,bad);
    inverse = __shfl_sync(0xffffffffu,inverse,0);
    for (int j = lane; j < keys; j += 32) own[j] = mul_(own[j],inverse,bad);
    __syncwarp();
#pragma unroll 1
    for (int d = lane; d < DIM; d += 32) {
      PrefillTree t; t.n=0;
      for (int first = 0; first < keys; first += 32) {
        const int rows = keys - first < 32 ? keys - first : 32;
        float group[4];
#pragma unroll
        for (int g = 0; g < 4; ++g) {
          const int base = 8*g, valid = rows-base < 8 ? rows-base : 8;
          float terms[8] = {};
#pragma unroll
          for (int b = 0; b < 8; ++b) if (b < valid)
            terms[b] = mul_(own[first+base+b],kv[(first+base+b)*padded+d+(d>>5)],bad);
#pragma unroll
          for (int s = 1; s < 8; s <<= 1) {
#pragma unroll
            for (int b = 0; b < 8; b += 2*s) if (b+s < valid) terms[b] = add_(terms[b],terms[b+s],bad);
          }
          group[g]=terms[0];
        }
        const int present = (rows+7)>>3;
        if (present > 1) group[0]=add_(group[0],group[1],bad);
        if (present > 3) group[2]=add_(group[2],group[3],bad);
        if (present > 2) group[0]=add_(group[0],group[2],bad);
        prefill_push(t,group[0],bad);
      }
      out[(size_t)i*heads*DIM+h*DIM+d]=prefill_finish(t,bad);
    }
  }
  report(error,bad);
}
