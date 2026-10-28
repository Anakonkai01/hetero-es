# B22 streamed activation loads with ldmatrix

Selected source: `eebf689f`. The pilot changes producer/consumer swizzles so the MMA activation fragments
can be loaded with `ldmatrix.m8n8.x4.shared.b16`. Weight fragments use matching canonical four-byte K
halves. Exact signed-byte products, degree accumulation and final encoding are unchanged. Selection is
restricted to **B22 SM120**; B14 and other architectures retain scalar fragment loads. The prototype diff
is retained, while the selected source adds explicit scoped policy and cache/identity fields.

**119 GPU stream/group/fused tests** pass (396.75 s), including independent CPU oracles and PTX/SASS code
generation for SM80/86/89/90/120. Only SM120 executes the new selected route on hardware in this directory.
ABAB Qwen B32 full-generation controls, against `267ba0b5`, have equal token hashes and improve short32
by **1.68%**, chat128 by **1.88%** (mean of two round medians). This is not a measured combined gain with
the separate host change. Combined frozen-source tests/mutations are tracked in their own directory.

## What this does NOT show

Offline instruction generation is not hardware qualification on untested architectures. This directory
does not by itself prove full trained/native/package/managed lifecycle acceptance or the 80% goal.
