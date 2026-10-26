"""Experimental key-split strict decode attention; compiled with the audited arithmetic helpers in strict_cuda.

Decode attention of one query per sequence was one CTA per (sequence, KV head) walking every key, so the
longest sequence set the time while most SMs idled. Here every aligned 32-key chunk of a sequence is its own
CTA. Two launches keep the reference order exactly:

1. scores: each chunk CTA writes its rounded scores; the last chunk CTA of a (sequence, KV head) (an atomic
   ticket after a fence) computes the maximum, exponentials, denominator tree and normalized weights.
2. values: each chunk CTA reduces its 32-key tile to the tile root; the last one pushes the roots in order.

The block denominator tree is the aligned pruned in-place tree and the value counter reduces aligned tile
roots in order, so splitting at aligned 32-key chunks reproduces every rounded operation of
strict_attention_gqa. Each K/V element is loaded, flushed and checked once; the error bits are only ORed.
Tickets are reset by the CTA that consumes them, and a fresh zeroed ticket plane is passed on every call.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class KeysplitAttentionPlan:
    chunks: int
    shared_bytes: int


def keysplit_attention_plan(dim, repeats, max_keys):
    """One 32-key chunk per CTA, block (dim, repeats). The scores CTA reuses its shared tile for the
    [repeats][max_keys] denominator tree, so the bound is the larger of the two within 48 KiB."""
    if (
        any(type(n) is not int for n in (dim, repeats, max_keys))
        or dim not in (32, 64, 128, 256)
        or not 1 <= repeats
        or repeats * dim > 512
        or not 1 <= max_keys <= 4096
    ):
        return None
    padded = dim + dim // 32
    shared = 4 * max((repeats + 32) * padded, repeats * max_keys)
    if shared > 48 * 1024:
        return None
    return KeysplitAttentionPlan(-(-max_keys // 32), shared)


_KEYSPLIT_SOURCE = r"""
#define THREADS (DIM * REPEATS)
#define LANES (DIM / 32)
#define PADDED (DIM + LANES)
#define STAGED ((8 * DIM + THREADS - 1) / THREADS)  // float4 values of a 32-row tile per thread
// Rows [first, first + rows) of a [keys][DIM] plane: fetch into registers, then flush, check and store them in
// tile[32][PADDED] (one pad after 32 channels). The next chunk is fetched while the current one is used.
__device__ __forceinline__ void keysplit_fetch(float4* staged, const float* base, int first, int rows, int tid) {
  const float4* source = reinterpret_cast<const float4*>(base + (size_t)first * DIM);
  const int count = (rows * DIM) >> 2;
#pragma unroll
  for (int u = 0; u < STAGED; ++u)
    if (tid + u * THREADS < count) staged[u] = source[tid + u * THREADS];
}
__device__ __forceinline__ void keysplit_store(float* tile, const float4* staged, int rows, int tid, unsigned& bad) {
  const int count = (rows * DIM) >> 2;
#pragma unroll
  for (int u = 0; u < STAGED; ++u) {
    const int index = tid + u * THREADS;
    if (index < count) {
      const int element = index << 2, row = element / DIM, column = element & (DIM - 1);
      float* target = tile + row * PADDED + column + (column >> 5);
      target[0] = flush(staged[u].x);
      target[1] = flush(staged[u].y);
      target[2] = flush(staged[u].z);
      target[3] = flush(staged[u].w);
      note(target[0], bad);
      note(target[1], bad);
      note(target[2], bad);
      note(target[3], bad);
    }
  }
}

// Claim the ticket of (sequence, KV head) after this CTA's chunks; true for the last of `parts` CTAs.
__device__ __forceinline__ bool keysplit_last(int* ticket, int parts) {
  __shared__ int last;
  __threadfence();
  __syncthreads();
  if (threadIdx.x == 0 && threadIdx.y == 0) {
    last = atomicAdd(ticket, 1) == parts - 1;
    if (last) *ticket = 0;
  }
  __syncthreads();
  if (last) __threadfence();
  return last;
}

// Grid (queries, KV heads, splits): CTA z owns chunks z, z + splits, ... of its sequence's keys.
extern "C" __global__ void __launch_bounds__(THREADS) strict_attention_keysplit_scores(
    const float* q, const float* key, float* scores, int* tickets, int* error, const int* ranges, int heads,
    int length, int total_keys, int max_keys, float scale) {
  const int i = blockIdx.x, kv = blockIdx.y, x = threadIdx.x, r = threadIdx.y;
  const int tid = r * DIM + x, h = kv * REPEATS + r;
  const int start = ranges[3 * i], keys = ranges[3 * i + 1], limit = ranges[3 * i + 2];
  const int chunks = (keys + 31) >> 5, splits = gridDim.z;
  if ((int)blockIdx.z >= chunks) return;
  extern __shared__ float shared[];
  float* query = shared;                    // [REPEATS][PADDED]
  float* tile = query + REPEATS * PADDED;   // [32][PADDED]
  __shared__ float maxima[(THREADS + 31) / 32];
  unsigned bad = 0;
  query[r * PADDED + x + (x >> 5)] = load(q + ((size_t)h * length + i) * DIM + x, bad);
  const float* keys_base = key + ((size_t)kv * total_keys + start) * DIM;
  float* plane = scores + (size_t)i * heads * max_keys;  // [heads][max_keys] of this query
  // Score lanes as in strict_attention_gqa: thread tid serves key row (tid / LANES) & 31 of head tid / (32 LANES).
  const int lane = tid & (LANES - 1), score_row = (tid / LANES) & 31, score_head = tid / (LANES * 32);
  float4 staged[STAGED];
  keysplit_fetch(staged, keys_base, blockIdx.z << 5, keys - (int)(blockIdx.z << 5) < 32 ? keys - (blockIdx.z << 5) : 32, tid);
#pragma unroll 1
  for (int first = blockIdx.z << 5; first < keys; first += splits << 5) {
    const int rows = keys - first < 32 ? keys - first : 32, next = first + (splits << 5);
    __syncthreads();  // the previous chunk's tile is no longer read
    keysplit_store(tile, staged, rows, tid, bad);
    __syncthreads();
    if (next < keys) keysplit_fetch(staged, keys_base, next, keys - next < 32 ? keys - next : 32, tid);
    const bool live = score_row < rows;
    float v = 0.0f;
    if (live) {
      const float* own = query + score_head * PADDED + lane * 33;
      const float* row = tile + score_row * PADDED + lane * 33;
      float group[4];
#pragma unroll
      for (int g = 0; g < 4; ++g) {
        float terms[8];
#pragma unroll
        for (int item = 0; item < 8; ++item) terms[item] = mul_(own[8 * g + item], row[8 * g + item], bad);
#pragma unroll
        for (int stride = 1; stride < 8; stride <<= 1) {
#pragma unroll
          for (int item = 0; item < 8; item += 2 * stride) terms[item] = add_(terms[item], terms[item + stride], bad);
        }
        group[g] = terms[0];
      }
      v = add_(add_(group[0], group[1], bad), add_(group[2], group[3], bad), bad);
    }
#pragma unroll
    for (int stride = 1; stride < LANES; stride <<= 1) {
      float other = __shfl_down_sync(0xffffffffu, v, stride, LANES);
      if (live && (lane & (2 * stride - 1)) == 0) v = add_(v, other, bad);
    }
    if (live && lane == 0) plane[(kv * REPEATS + score_head) * max_keys + first + score_row] = mul_(v, scale, bad);
  }
  if (!keysplit_last(tickets + i * gridDim.y + kv, chunks < splits ? chunks : splits)) {
    report(error, bad);
    return;
  }
  // The last CTA: softmax of every key for head r, exactly as strict_attention_gqa.
  float* own_scores = plane + h * max_keys;
  float* own_tree = shared + r * max_keys;
  __syncthreads();  // every read of the shared query and tile is retired before they hold the scores
  // Four independent L2 reads in flight per thread (scores written by the other chunk CTAs).
#pragma unroll 1
  for (int j = x; j < keys; j += 4 * DIM) {
    float s[4];
#pragma unroll
    for (int u = 0; u < 4; ++u) s[u] = j + u * DIM < keys ? __ldcg(own_scores + j + u * DIM) : 0.0f;
#pragma unroll
    for (int u = 0; u < 4; ++u) if (j + u * DIM < keys) own_tree[j + u * DIM] = s[u];
  }
  __syncthreads();
  float local = -FLT_BIG;
#pragma unroll 1
  for (int j = x; j < keys; j += DIM) {
    const float s = own_tree[j];
    if (j <= limit && s > local) local = s;
  }
  for (int offset = 16; offset >= 1; offset >>= 1) {
    float other = __shfl_xor_sync(0xffffffffu, local, offset);
    local = other > local ? other : local;
  }
  if ((tid & 31) == 0) maxima[tid >> 5] = local;
  __syncthreads();
  float maximum = -FLT_BIG;
  for (int w = (r * DIM) >> 5; w < ((r + 1) * DIM) >> 5; ++w) maximum = maxima[w] > maximum ? maxima[w] : maximum;
  if (__float_as_uint(maximum) == 0x80000000u) maximum = 0.0f;  // the reference maps a -0 maximum to +0
#pragma unroll 4
  for (int j = x; j < keys; j += DIM) {
    bool allowed = j <= limit;
    float shifted = add_(allowed ? own_tree[j] : maximum, -maximum, bad);
    float e = exp_(shifted, bad);
    float n = allowed ? e : 0.0f;
    own_scores[j] = n;  // read back below by this same thread
    own_tree[j] = n;
  }
  __syncthreads();
  for (int stride = 1; stride < keys; stride <<= 1) {
#pragma unroll 1
    for (int j = x * 2 * stride; j < keys; j += DIM * 2 * stride)
      if (j + stride < keys) own_tree[j] = add_(own_tree[j], own_tree[j + stride], bad);
    __syncthreads();
  }
  float denominator = own_tree[0];
  float inverse = reciprocal_(denominator == 0.0f ? 1.0f : denominator, bad);
#pragma unroll 1
  for (int j = x; j < keys; j += DIM) own_scores[j] = mul_(own_scores[j], inverse, bad);
  report(error, bad);
}

extern "C" __global__ void __launch_bounds__(THREADS) strict_attention_keysplit_values(
    const float* value, const float* scores, float* partials, float* out, int* tickets, int* error,
    const int* ranges, int heads, int length, int total_keys, int max_keys) {
  const int i = blockIdx.x, kv = blockIdx.y, x = threadIdx.x, r = threadIdx.y;
  const int tid = r * DIM + x, h = kv * REPEATS + r;
  const int start = ranges[3 * i], keys = ranges[3 * i + 1];
  const int chunks = (keys + 31) >> 5, splits = gridDim.z;
  if ((int)blockIdx.z >= chunks) return;
  __shared__ float tile[32 * PADDED];
  __shared__ float weights[REPEATS][32];
  unsigned bad = 0;
  const float* values_base = value + ((size_t)kv * total_keys + start) * DIM;
  const float* own_scores = scores + ((size_t)i * heads + h) * max_keys;
  float* roots = partials + (size_t)(i * gridDim.y + kv) * (max_keys >> 5) * THREADS;  // [chunk][THREADS]
  const int channel = x + (x >> 5);
  float4 staged[STAGED];
  keysplit_fetch(staged, values_base, blockIdx.z << 5, keys - (int)(blockIdx.z << 5) < 32 ? keys - (blockIdx.z << 5) : 32, tid);
  float weight = x < 32 && (int)(blockIdx.z << 5) + x < keys ? own_scores[(blockIdx.z << 5) + x] : 0.0f;
#pragma unroll 1
  for (int first = blockIdx.z << 5; first < keys; first += splits << 5) {
    const int rows = keys - first < 32 ? keys - first : 32, next = first + (splits << 5);
    __syncthreads();  // the previous chunk's tile and weights are no longer read
    keysplit_store(tile, staged, rows, tid, bad);
    if (x < 32) weights[r][x] = weight;
    __syncthreads();
    if (next < keys) {
      keysplit_fetch(staged, values_base, next, keys - next < 32 ? keys - next : 32, tid);
      weight = x < 32 && next + x < keys ? own_scores[next + x] : 0.0f;
    }
    float group[4];
#pragma unroll
    for (int g = 0; g < 4; ++g) {
      const int base = 8 * g, valid = rows - base < 8 ? rows - base : 8;  // valid <= 0: group absent
      float terms[8] = {};
#pragma unroll
      for (int item = 0; item < 8; ++item)
        if (item < valid) terms[item] = mul_(weights[r][base + item], tile[(base + item) * PADDED + channel], bad);
#pragma unroll
      for (int stride = 1; stride < 8; stride <<= 1) {
#pragma unroll
        for (int item = 0; item < 8; item += 2 * stride)
          if (item + stride < valid) terms[item] = add_(terms[item], terms[item + stride], bad);
      }
      group[g] = terms[0];
    }
    const int present = (rows + 7) >> 3;  // pruned aligned tree over this tile's groups
    if (1 < present) group[0] = add_(group[0], group[1], bad);
    if (3 < present) group[2] = add_(group[2], group[3], bad);
    if (2 < present) group[0] = add_(group[0], group[2], bad);
    roots[(first >> 5) * THREADS + tid] = group[0];
  }
  if (!keysplit_last(tickets + i * gridDim.y + kv, chunks < splits ? chunks : splits)) {
    report(error, bad);
    return;
  }
  Tree t;
  t.n = 0;
  for (int k = 0; k < chunks; k += 4) {
    float root[4];
#pragma unroll
    for (int u = 0; u < 4; ++u) root[u] = k + u < chunks ? __ldcg(roots + (k + u) * THREADS + tid) : 0.0f;
#pragma unroll
    for (int u = 0; u < 4; ++u) if (k + u < chunks) push(t, root[u], bad);
  }
  out[(size_t)i * heads * DIM + h * DIM + x] = finish(t, bad);
  report(error, bad);
}
"""
