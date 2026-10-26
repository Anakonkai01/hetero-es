"""Bounded decode layout/KV movement and strict greedy selection, safe inside CUDA Graph capture.

No new forward arithmetic: KV copies preserve bits; the repetition penalty reuses the reference rounded
multiply and reciprocal constants. Comparisons select the smallest token ID on an exact tie.
"""

import torch

from heteroes.eval import strict_cuda as sc

GREEDY_CHUNK = 8192  # columns per CTA of the split greedy selection (matches the kernel source)

_SOURCE = (
    sc._OPS_SOURCE.split("// Binary-counter reduction")[0]
    + r"""
extern "C" __global__ void decode_layout(const long long* owners, const int* lengths, int* ranges,
                                         long long* positions, int* error, int active, int capacity, int context) {
  int i = blockIdx.x * blockDim.x + threadIdx.x;
  if (i >= active) return;
  long long owner = owners[i];
  int position = owner >= 0 && owner < capacity ? lengths[owner] : -1;
  bool valid = owner >= 0 && owner < capacity && position >= 1 && position < context;
  if (!valid) atomicOr(error, 4);
  positions[i] = valid ? position : 0;
  ranges[3*i] = valid ? (int)owner * context : 0;
  ranges[3*i+1] = valid ? position+1 : 1;
  ranges[3*i+2] = valid ? position : 0;
}

// k: [heads, active, dim]; v: [active, heads*dim]. Cache: [heads, capacity*context, dim].
extern "C" __global__ void decode_store(const float* k, const float* v, const int* ranges,
                                        float* keys, float* values, int active, int total, int heads, int dim) {
  int i=blockIdx.x, h=blockIdx.y, d=threadIdx.x;
  if (d >= dim) return;
  int p=ranges[3*i]+ranges[3*i+1]-1;
  keys[((size_t)h*total+p)*dim+d]=k[((size_t)h*active+i)*dim+d];
  values[((size_t)h*total+p)*dim+d]=v[((size_t)i*heads+h)*dim+d];
}

// Prefix source: [heads, source_tokens, dim]. Each range is (source start, length, destination start).
extern "C" __global__ void decode_prefix(const float* k, const float* v, const int* spans,
                                         float* keys, float* values, int source_tokens, int total, int dim) {
  int i=blockIdx.x, h=blockIdx.y, d=threadIdx.x;
  if (d >= dim) return;
  int start=spans[3*i], length=spans[3*i+1], dest=spans[3*i+2];
  for(int p=blockIdx.z;p<length;p+=gridDim.z) {
    keys[((size_t)h*total+dest+p)*dim+d]=k[((size_t)h*source_tokens+start+p)*dim+d];
    values[((size_t)h*total+dest+p)*dim+d]=v[((size_t)h*source_tokens+start+p)*dim+d];
  }
}

extern "C" __global__ void decode_greedy(const float* scores, unsigned char* seen, const long long* owners,
                                         long long* tokens, long long* result, int* error, int active, int vocab, int apply_penalty,
                                         float penalty, float inverse) {
  int i=blockIdx.x, t=threadIdx.x;
  size_t owner=(size_t)owners[i];
  unsigned bad=0;
  float best=-FLT_BIG;
  int index=vocab;
  for(int j=t;j<vocab;j+=256) {
    float s=load(scores+(size_t)i*vocab+j,bad);
    if(apply_penalty && seen[owner*vocab+j]) s=mul_(s,s < 0.0f ? penalty : inverse,bad);
    if(s > best || (s == best && j < index)) {best=s;index=j;}
  }
  for(int offset=16;offset>=1;offset>>=1) {
    float other=__shfl_xor_sync(0xffffffffu,best,offset);
    int id=__shfl_xor_sync(0xffffffffu,index,offset);
    if(other > best || (other == best && id < index)) {best=other;index=id;}
  }
  __shared__ float maxima[8];
  __shared__ int indices[8];
  if((t&31)==0) {maxima[t>>5]=best;indices[t>>5]=index;}
  __syncthreads();
  if(t==0) {
    for(int w=0;w<8;++w) {
      float other=maxima[w];int id=indices[w];
      if(other > best || (other == best && id < index)) {best=other;index=id;}
    }
    // Every score failure is reported before the separate status-publishing kernel. Keep writes bounded
    // even when no finite score could be selected; the host will refuse the complete result.
    if(index >= vocab) {bad |= 1u;index=0;}
    tokens[owner]=index;
    seen[owner*vocab+index]=1;
    result[i]=index;
  }
  if(bad) atomicOr(error,(int)bad);
}

// decode_greedy split over GREEDY_CHUNK-column chunks: the selection (largest score, smallest index on a tie;
// NaN never selected) is order-independent, so per-chunk winners combined in any order give the same token.
#define GREEDY_CHUNK 8192
extern "C" __global__ void decode_greedy_chunks(const float* scores, const unsigned char* seen, const long long* owners,
                                                float* best_scores, int* best_indices, int* error, int vocab,
                                                int apply_penalty, float penalty, float inverse) {
  const int chunk = blockIdx.x, i = blockIdx.y, t = threadIdx.x, chunks = gridDim.x;
  const size_t owner = (size_t)owners[i];
  const int end = vocab - chunk * GREEDY_CHUNK < GREEDY_CHUNK ? vocab : (chunk + 1) * GREEDY_CHUNK;
  unsigned bad = 0;
  float best = -FLT_BIG;
  int index = vocab;
  for (int j = chunk * GREEDY_CHUNK + t; j < end; j += 256) {
    float s = load(scores + (size_t)i * vocab + j, bad);
    if (apply_penalty && seen[owner * vocab + j]) s = mul_(s, s < 0.0f ? penalty : inverse, bad);
    if (s > best || (s == best && j < index)) {best = s; index = j;}
  }
  for (int offset = 16; offset >= 1; offset >>= 1) {
    float other = __shfl_xor_sync(0xffffffffu, best, offset);
    int id = __shfl_xor_sync(0xffffffffu, index, offset);
    if (other > best || (other == best && id < index)) {best = other; index = id;}
  }
  __shared__ float maxima[8];
  __shared__ int indices[8];
  if ((t & 31) == 0) {maxima[t >> 5] = best; indices[t >> 5] = index;}
  __syncthreads();
  if (t == 0) {
    for (int w = 0; w < 8; ++w) {
      float other = maxima[w]; int id = indices[w];
      if (other > best || (other == best && id < index)) {best = other; index = id;}
    }
    best_scores[i * chunks + chunk] = best;
    best_indices[i * chunks + chunk] = index;
  }
  if (bad) atomicOr(error, (int)bad);
}

extern "C" __global__ void decode_greedy_select(const float* best_scores, const int* best_indices, unsigned char* seen,
                                                const long long* owners, long long* tokens, long long* result,
                                                int* error, int vocab, int chunks) {
  const int i = blockIdx.x;
  if (threadIdx.x) return;
  const size_t owner = (size_t)owners[i];
  float best = -FLT_BIG;
  int index = vocab;
  for (int c = 0; c < chunks; ++c) {
    float other = best_scores[i * chunks + c]; int id = best_indices[i * chunks + c];
    if (other > best || (other == best && id < index)) {best = other; index = id;}
  }
  // As decode_greedy: report a row without a selectable score, keep the writes bounded.
  if (index >= vocab) {atomicOr(error, 1); index = 0;}
  tokens[owner] = index;
  seen[owner * vocab + index] = 1;
  result[i] = index;
}

// Kernel ordering is the global barrier between arithmetic/selection flags and host publication.
extern "C" __global__ void decode_publish(const long long* owners, int* lengths, const int* error,
                                          long long* result, int active, int advance) {
  int i=threadIdx.x;
  if(i<active && advance) ++lengths[owners[i]];
  if(i==0) result[active]=*error;
}
"""
)


class DecodeKernels:
    def __init__(self, kernels):
        self.kernels = kernels
        header = "".join(f"#define {k} 0x{v:08x}u\n" for k, v in sc.reference_constants().items())
        self.functions = kernels._compile(
            "decode-graph-ops",
            header + _SOURCE,
            [
                "decode_layout",
                "decode_store",
                "decode_prefix",
                "decode_greedy",
                "decode_greedy_chunks",
                "decode_greedy_select",
                "decode_publish",
            ],
            ptx_exact=sc.OPS_PTX_EXACT,
            sass_exact=sc.OPS_SASS_EXACT,
        )

    def layout(self, owners, lengths, ranges, positions, flag, capacity, context):
        self.kernels._launch(
            self.functions["decode_layout"],
            grid=1,
            block=(256, 1),
            pointers=(owners, lengths, ranges, positions, flag),
            integers=(owners.numel(), capacity, context),
        )

    def store(self, key, value, ranges, keys, values):
        heads, total, dim = keys.shape
        active = value.shape[0]
        self.kernels._launch(
            self.functions["decode_store"],
            grid=(active, heads),
            block=(32 * -(-dim // 32), 1),
            pointers=(key, value, ranges, keys, values),
            integers=(active, total, heads, dim),
        )

    def prefix(self, key, value, spans, keys, values):
        heads, total, dim = keys.shape
        self.kernels._launch(
            self.functions["decode_prefix"],
            grid=(spans.shape[0], heads, 16),  # positions are strided over 16 CTAs per sequence and head
            block=(32 * -(-dim // 32), 1),
            pointers=(key, value, spans, keys, values),
            integers=(key.shape[1], total, dim),
        )

    def greedy(self, scores, seen, owners, tokens, result, flag, penalty, inverse):
        active, vocab = owners.numel(), scores.shape[1]
        chunks = -(-vocab // GREEDY_CHUNK)
        if chunks == 1:
            self.kernels._launch(
                self.functions["decode_greedy"],
                grid=active,
                block=(256, 1),
                pointers=(scores, seen, owners, tokens, result, flag),
                integers=(active, vocab, int(penalty != 1.0)),
                floats=(penalty, inverse),
            )
            return
        # Wide vocabularies: one CTA per row and chunk, then an in-order combination of the chunk winners.
        best = torch.empty((active, chunks), dtype=torch.float32, device=scores.device)
        indices = torch.empty((active, chunks), dtype=torch.int32, device=scores.device)
        self.kernels._launch(
            self.functions["decode_greedy_chunks"],
            grid=(chunks, active),
            block=(256, 1),
            pointers=(scores, seen, owners, best, indices, flag),
            integers=(vocab, int(penalty != 1.0)),
            floats=(penalty, inverse),
        )
        self.kernels._launch(
            self.functions["decode_greedy_select"],
            grid=active,
            block=(32, 1),
            pointers=(best, indices, seen, owners, tokens, result, flag),
            integers=(vocab, chunks),
        )

    def publish(self, owners, lengths, flag, result, *, advance):
        self.kernels._launch(
            self.functions["decode_publish"],
            grid=1,
            block=(256, 1),
            pointers=(owners, lengths, flag, result),
            integers=(owners.numel(), int(advance)),
        )
