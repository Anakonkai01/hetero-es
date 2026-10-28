# Unselected strict suffix verification decoder

Base selected runtime remains B22 `b1ef257a`; evidence HEAD at experiment entry was `ef21c7c3`.
The new generator is a scratch prototype. No runtime, managed default or historical recipe changed.

The generator uses prior completion token IDs as suffix-based proposals. Every output is verified
by the current candidate's B22 projections and strict nonlinear operators. It stores one primary
FP16 model, current-candidate KV, small row-scale metadata, and one retained speculative capture.
An earlier candidate's KV, activations, logits or parameters are never reused. The parent proposal
bank is CPU token data, bounded to 32,768 source tokens; suffix keys have lengths 2–8.

Each query's key range ends at its own hypothetical position. Only the matching proposed prefix
and the current model's next token are emitted. Later rejected KV positions are overwritten before
they can enter a new true prefix. EOS stops publication inside a verified block before its bonus
token, and context tails reduce the block to one. Repetition penalty other than one or disabled
cache explicitly uses the ordinary graph. Arbitrary full API/lifecycle acceptance is not claimed.

Numeric/domain failure in an unaccepted future branch triggers a fresh one-position strict score
at the real prefix. A failure on that true path still raises. CUDA/infrastructure exceptions raise;
they are never submitted as rewards. A constructed untied Llama fixture has a finite all-zero true
path while a proposed token causes overflow in a later layer; the test verifies successful fallback
and unchanged CPU tokens. This is exercised on both surveyed GPU architectures.

## Correctness receipts

- Final source: six GPU tests on 5070 Ti and six on 3060 WSL2, plus two CPU proposal tests on each.
  Qwen2/wider-head Llama fixtures compare against the independent CPU integer decoder through
  correct/wrong/empty proposals, changed weights and restore, EOS, context tails, bad-proposal
  cleanup, a replaced Parameter and a changed CUDA stream. Request buffers are checked cleared.
- A dedicated EOS fixture forces EOS inside an accepted block while another owner is already
  finished; repeated calls verify capture reuse. `gpu-5070ti-05.log` checks the final added assertion;
  the remote six-test run includes it. Earlier passing stages are retained separately.
- All three scratch mutants are killed: accepting a rejected proposal, publishing beyond EOS,
  and failing the candidate instead of retrying its finite true path after bad speculation.
- Initial red import and an early release-time InferenceMode error remain in the logs; the latter
  is fixed by entering inference mode while clearing retained request tensors.

The approved 3060 standalone test used the existing selected source stage, matching source archive
manifest and process-local CUDA library path. It did not change worker approval/contribution state.
This is not native Windows, trained heterogeneous candidate or managed acceptance of this decoder.

## Whole-generation measurements

One trained Qwen2.5-0.5B model is shared across ordinary B22 and the speculative wrappers. The CPU
canonical snapshot and frozen noise v2 create parent and seed 7001 ± at sigma 0.001, with exact
restore verified. Prompts are the first one/eight rows of the sealed GSM8K chat workload. Each row
emits exactly 128 tokens; EOS stopping is disabled. Warmup is excluded, then ABCCBA gives ten host
wall samples per variant. Every generated token must equal ordinary B22 in every repeat.

`suffix` uses only the original parent's completion as proposal data. `empty` uses the same new
generator with no proposal. The parent case's bank is its own earlier completion, so that row is
a favorable repeat control, not evidence of candidate generalization.

| V1 state / batch / block | Ordinary B22 token/s | Suffix token/s | Speed ratio |
| --- | ---: | ---: | ---: |
| Parent / 1 / 4 | 243.5 | 858.9 | 3.527 |
| Plus / 1 / 4 | 243.0 | 317.2 | 1.305 |
| Minus / 1 / 4 | 243.0 | 596.0 | 2.452 |
| Parent / 8 / 2 | 1,667.7 | 2,340.1 | 1.403 |
| Plus / 8 / 2 | 1,665.9 | 1,242.3 | 0.746 |
| Minus / 8 / 2 | 1,665.9 | 1,181.8 | 0.709 |

The batch-one candidate gains are real within this single-prompt pilot, conditional on already
having the parent bank. The empty generator stays around 1.01x ordinary B22 at batch one. This
does not justify choosing batch one over a faster larger batch or claim general ES acceleration.

V1 captures again when active row count changes: plus/minus batch-eight calls capture six/eight
times. A finite V2 keeps query rows stable when possible. A finished owner recomputes its own last
block of original prompt tokens at their real positions; no post-EOS branch is evaluated, no live
owner's cache is aliased, and its predictions are discarded. Short prompts still compact safely.
The capture key also includes session identity, query count, block and metadata buffer pointers.

| V2 state / batch 8 / block 2 | Ordinary B22 token/s | Suffix token/s | Speed ratio |
| --- | ---: | ---: | ---: |
| Plus | 1,667.5 | 1,577.0 | 0.946 |
| Minus | 1,666.4 | 1,619.1 | 0.972 |

V2 eliminates repeated captures in timed calls, but still loses at batch eight. The slowest rows
need 122/118 rounds versus 127 ordinary post-prefill rounds; accepted tokens elsewhere do not
remove that batch barrier. The empty batch-eight generator is about 0.913x ordinary B22. Stop
expanding this fixed-block implementation; it does not improve the primary throughput path.

Parent-bank creation including initial warmup takes 3.67/3.73 seconds in the two processes and is
recorded separately, outside the table's warm generation times. It is not amortized into a claimed
ES speedup. Peak Torch allocated memory is 1.253/1.235 GiB across the shared-model wrappers in the
respective processes. These are allocator observations, not complete resource qualification.

The V1 benchmark and source snapshots are retained explicitly. `source-02-manifest.json` pins V2
and the remote test bundle; final harness files and SHA256 sums are included. Reproduce with
`PYTHONPATH=runtime/src:runtime/tests/eval:<folder>/harness`, the isolated Python, GPU opt-in and
benchmark `--gpu`. Local model/cache paths are recorded in the harness.

Next primary work returns to full-weight projection throughput. A small-batch optional proposal
decoder may be revisited after broader corpus/candidate, portable/native and lifecycle evidence;
it must not be used to close the own-kernel near-vLLM objective.

## What this does NOT show

A selected optimization or default, batch-eight/32 speedup, general ES or learning benefit, native
Windows acceptance, trained cross-GPU proposal invariance, full precision/resource/ownership/failure
qualification, or near-vLLM throughput. Do not compare these chat/128 batch-one numbers with earlier
short/32 vLLM controls. No push, merge, deployment, device-state change or ai-environment change occurred.
