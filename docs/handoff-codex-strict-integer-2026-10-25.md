# Strict integer continuation

The previous goal turn made concrete progress: implementation commit **`fb18a7b7`**, independent arithmetic proof/tests,
four-target regression, trained canonical-candidate equality, timing/counterexample receipts and a promising separate
exact-conversion prototype. The full [approved M0–M6 plan](PLAN-SUA-HUMAN-REVIEW.md) remains active and incomplete.
The user asked for autonomous overnight work, with highest priority on general performance approaching vLLM.
Do not narrow scope to this checkpoint or mark M1/M2 complete.

No push/merge/deploy, device approval/contribution changes, learning runs, sudo use, `ai` environment changes, Archive
or `/mnt/sekai` writes. GPU/SSH to all four session targets is authorized. No subagents are authorized by current
developer instructions. All owned tests/benchmarks/prototypes from this slice are terminal; no remote chain remains.

## Selected implementation and evidence

`eval/integer_reference.py`, `integer_cuda.py`, `integer_decoder.py` are a **separate** experimental arithmetic:
row-local scales, B14/B22 exact integer RNE quantization, signed int8 MMA with bounded degree accumulators and int64
reconstruction, exact scaled-integer FP32 RNE then signed FTZ, existing strict FP32 nonlinearities. B22 is the new
decoder default. No old arithmetic identity/default/recipe was replaced. Read the
[contract](../runtime/docs/integer-projection-v1.md) and
[selected-source results](evidence/2026-10-25-strict-integer/RESULTS-01.md).

Weight exponents are refreshed at **every locked generation entry**, checked before prefill/capture, reused only
within that request, then cleared/synchronized before unlock. They use weak binding references, not a pointer-only
content cache. No full quantized/FP32 weight copy. `StrictDecoderGraph` now has protected begin/end/workspace hooks;
its default FP32 numerical kernels are unchanged. Standalone projection/forward refreshes metadata per call.

- Check-all ALL PASS: runtime **3016 passed / 285 skipped**, backend **452 passed** (existing warning), all other checks.
- **301 selected tests passed on each of four GPUs** (including CPU reference checks): local/Nhut 5070 Ti Linux,
  Thao/Quang 3060 WSL2. Four small graph layouts, both precisions, live exponent-changing weights, physical codec
  boundaries, SIMD/MMA/split variants, request isolation/rebind/errors and legacy strict regressions.
- Scratch mutations **11/11**, controls pass. Linux source-copy apps pass; Worker source and Server embedded SDK
  match five source hashes. Build reports starting HEAD `abe40dd9`; hashes identify the committed working source.
- Three local trained checkpoints: SmolLM2-360M, TinyLlama-1.1B, Qwen2.5-0.5B. Parent, seed 7001 at ±1e-3 and
  restored parent. All exact weight restores and restored inference pass. B22 matches the old tree's finite tokens;
  B14 changes one Qwen minus-candidate stream. Keep that counterexample; do not call this general quality acceptance.
- Smol/Qwen full asset manifests, source/operator identities, canonical weight hashes, logits/token/text/reward
  match on local 5070 Ti and Thao 3060 for every measured state. TinyLlama trained cross-GPU remains open.
- Selected B22 local B1/B32 total token/s: **177.1/1318.2 Smol, 114.5/830.7 Tiny, 171.8/1358.5 Qwen**. B32 is
  1.64–2.88x old FP32 but only 9–11% prior vLLM default; B1 regresses. Goal performance is not reached.

The new asset-only inputs under `.scratch/strict-integer-20261025/models/{smol,tiny,qwen}` hardlink the original
safe assets. Previous Smol `.cache/huggingface/trees/*.json` receipts remain unchanged. New cross-GPU manifests match
fully. Prior vLLM comparisons explicitly compare consumed assets and retain full-manifest inequality for old Smol.

## Immediate performance work

The **unselected** exact-conversion variant has now passed its first feasibility gates. Read
[scratch results](evidence/2026-10-25-strict-integer/CVT-RESULTS-01.md).

Source: `.scratch/strict-integer-20261025/cvt-prototype-01/src/heteroes/eval/{integer_cuda,strict_cuda}.py`, also copied
immutably into the evidence directory. Only weight `quant_half` and integer-module conversion audit change.
It widens FP16 exactly, adjusts FP32 exponent bits (scaled magnitude always normal and <2^B), then uses PTX
`cvt.rni.s32.f32`. No FP multiply. Its SASS is allowed only for the observed exact integer conversion instructions.

All **1,017,852 admitted finite FP16 value/row-exponent pairs per precision** match the independent exact-power-of-two
FP64 oracle on Nhut/Thao. **99 reference/operator/decoder tests** pass per target. Local trained parent/±/restored
logits, tokens, text/rewards equal baseline for all three engines; `cvt-trained-comparison-01.json` asserts fields.
Scratch B22 local B1/B8/B32:

| Model | B1 | B8 | B32 |
| --- | ---: | ---: | ---: |
| SmolLM2-360M | 249.4 | 497.9 | 1451.6 |
| TinyLlama-1.1B | 174.4 | 344.7 | 918.9 |
| Qwen2.5-0.5B | 254.7 | 531.3 | 1507.7 |

Next: make exhaustive finite-weight coverage a meaningful opt-in test, add conversion-audit checks **before** selecting
the variant, carry the normal-domain proof into the contract, run selected-source regression/packaging and compare
current source on all targets. No managed promotion from these finite checks. Prototype scripts and source are
retained; `quant-baseline-nhut-01/02` are harness mistakes (missing context initialization/empty integer args), not
arithmetic counterexamples. Corrected harness is `probe-half-quant-03.py`.

Then profile the faster trained decoder and attack B32 data reuse. Useful candidates:

1. Share activation quantization explicitly for Q/K/V and gate/up within one forward step; avoid caching activation
   contents by pointer across requests/replays. Consider `_project_many` and a prepared-input path, with independent
   component equality/error/alias tests and no concatenated/repacked full weights.
2. Reduce radix packing overhead with a defined PTX signed shift. Balanced digits satisfy next=floor((q+128)/256)
   for every admitted q; current exact division may leave extra signed-rounding instructions. Prove/test endpoints,
   carries and all admitted q in a scratch prototype; inspect actual PTX/SASS before selecting anything.
3. Tiled/shared on-the-fly weight packing and reuse, bounded workspace, shape/GPU tuning, split-K policy backed by
   end-to-end results. Previous explicit vector loads regressed; do not blindly restore them.

Preserve scalar/vector/split red receipts. `probe_linear.py` is an **old incompatible raw kernel signature**; do not run
it against current source. `probe_split.py` uses the public API and is current. Synthetic event timings exclude host
overhead and include per-call metadata; trained timings amortize scales over one request. Keep those scopes distinct.

## Reproduction and environments

Repo `/home/pc5070ti/projects/heteroes`, branch `fix/human-review-single-model-2026-10-24`.
Local GPU Python `/home/pc5070ti/miniforge3/envs/heteroes-match/bin/python`; CPU helper `.venv-backend/bin/python`.
Use `HETEROES_GPU_ACCEPTANCE=1` and `--gpu` for scripts; CPU `CUDA_VISIBLE_DEVICES=''`.

Remote selected-source stage: `/tmp/heteroes-strict-integer-20261025-02` on all three remotes, containing `src`,
`tests/eval`, `testdeps` and benchmark helpers. New quality script was copied separately to Thao.
Prototype: `/tmp/heteroes-integer-cvt-20261025-03` on Nhut; `...-01` on Thao. No background work remains.
SSH uses `/home/pc5070ti/.ssh/config -o BatchMode=yes`.

- Nhut: `heheboiz@100.108.195.50`, Python
  `/home/heheboiz/.local/share/heteroes-worker/runtimes/bf28fa656ad4/python/bin/python3`.
- Thao: `thao_nguyen@100.92.20.58`, Python
  `/home/thao_nguyen/.local/share/heteroes-c4-cpu/runtimes/9a553d2dfae9/python/bin/python3.12`.
- Quang: `quang@100.99.227.8`, Python `/home/quang/heteroes-venv/bin/python`.
- WSL process-local path:
  `LD_LIBRARY_PATH=/usr/lib/wsl/drivers/nv_dispi.inf_amd64_feedb8c0271ca811:/usr/lib/wsl/lib`.

Thao models: Smol disk-backed
`/home/thao_nguyen/.cache/heteroes-strict-models-20261025/SmolLM2-360M-Instruct/a10cc1512eabd3dde888204e902eca88bddb4951`;
Qwen `/home/thao_nguyen/.local/share/heteroes-c4-cpu/models/7ae557604adf67be50417f59c2c2f167def9a775`.
Local `/` has about 22 GiB free at this checkpoint; no cleanup was performed.

## Full scope still open

M0 broader all-phase measurements; M1 further performance/operator/trained-model/native Windows acceptance; M2
watchdogs/D11, D10 recovery and audit product projection; M3 bounded I/O/retention/replacement consistency; M4 managed
GPU ownership/recipe qualification/SDK/native packaging; M5 system/fault/throughput acceptance; M6 one frozen quantized
base plus floating LoRA format. [Effort split](HUMAN-REVIEW-EFFORT-SPLIT.md) keeps routine audit projection/UI for medium
effort and copy/examples for low effort. Remaining heavy work is not reassigned merely because this slice passed.
