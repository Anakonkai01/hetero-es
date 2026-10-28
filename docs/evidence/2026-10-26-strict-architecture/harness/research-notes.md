# Architectural experiments after projection ablation

Base selected runtime b1ef257a; receipt c9a6cf55; no runtime changes from new research yet.

Ablation is complete in projection-controls-5070ti-01.json. Short32/b32 B22 4349 token/s,
FP16 separate 7492, merged 7804. B22 prefill 60.7 ms/235.5 ms; read/wait 161.8 ms.
Chat128 first32GSM8k B22 3960, FP16 separate6073 merged6243. B22 prefill210/1034ms.
Vendor FP16 does NOT solve own strict/D2 goal; these are architectural controls.

Do not keep tuning bounded FP16 integer arithmetic: operator gains inconsistent; half2 does not
establish a compelling whole-model speedup. Preserve the independent proof/exhaustive quantizer
checks and stop this branch before quality/native promotion unless a new structural reason appears.

Next finite pilots:
1. Shared radix GEMM tiles: current four N warps each globally load the same packed A and hold two
   M groups' accumulators. Stage packed A once/CTA; quantize raw FP16 W into bounded shared radix
   tiles; use ldmatrix. Split warps over M and N to reduce per-thread accumulators and improve
   occupancy. Try N32/K32 (one N8 per warp) and N64/K64 (two N8 per warp), M16/M32, without changing
   B14/B22 arithmetic. Shared pitch K+16 bytes keeps 16B alignment and spreads bank addresses.
   Private cp.async raw double stages; CTA wait/barriers around producer/consumer phases.
   Preserve exact int32 degree bound and final integer reconstruction. No full transformed weights.
2. Capture prefill pure GPU core, with prepared positions/layout/last-index tensors and persistent
   static input buffers. Current eager packed prefill recreates views/launches every request.
   Validation, error reads and CPU tensor construction stay outside capture. Only one shape/model
   binding capture retained; include live weight-metadata buffer pointers in key; clear retained
   inputs/KV/logits at exit. Preserve numerical operations and candidate boundaries. A graph mixin
   can apply to B22 and the vendor ceiling control. Do NOT mistake vendor control for a strict result.
3. Optional attention pilot: key score currently one thread/key loops D, producing strided loads.
   A warp/key can load adjacent channels and merge aligned power-of-two subtrees with shuffles.
   Need exact pruned-tail tree and all masked-key nonfinite checks. Attention already loops actual
   key count; max_context only sizes shared allocation, not a padded compute loop.

Stop a pilot if it cannot show substantial whole-path benefit; do not spend native/three-model
qualification on small unselected operator wins. Owner explicitly cautioned against local tunneling.

Shared radix pilot 4 GPU oracle tests pass, but five Qwen shapes show insufficient gains:
N32/K32 ratios ~0.83,1.10,0.96,1.11,0.96; N64/K64 mostly regress. Stop tuning that branch.

New independent structural hypothesis: use tuned vendor batched GEMM for exact integer chunks.
PyTorch2.13 torch.bmm supports half inputs/F32 output; local API test reaches exact 2^24.
Keep A8/W8 arithmetic; each K chunk <=2^(24-a-w), disable reduced/F16 accumulation. Sum exact F32
integer partials in int64 then use original output encoder. Use fixed bounded quantized-W/partial
workspaces (32MiB/16MiB), never a full-model transformed cache. For rows>128 or shapes exceeding
scratch, use the same arithmetic's own kernel. Head remains B22. No claim this is a selected backend.
Two local GPU tests pass including integer oracle, live changes/restore, workspace clearing and
stream/precision guards. The five-shape vendor pilot completed: 0.948,1.148,1.290,1.315,0.957 versus
selected B22. No full-model or quality gate; stop these implementations rather than extend local tuning.

Captured prefill completed too: B22 4365 versus captured4364 short, 3953 versus captured3956 chat;
tokens agree but no useful speedup. Stop the capture branch.

Ordered direct-FP16/FP32 FMA256 pilot: 3 GPU tests pass, five operator speed ratios 0.276–0.840
versus B22. Slower in every case; stop. No new selected runtime gain from this research block.

Next work: attribute remaining whole-path GPU work and investigate fusion/attention with fixed
arithmetic gates; keep FP16 full-weight ES first, D2/D3 and native Windows direction. The vendor
projection control reaches only ~7804 token/s on short32, versus earlier vLLM control~13835, so
projection-only work cannot be assumed to close the measured end-to-end gap.
