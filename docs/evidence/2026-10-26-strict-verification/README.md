# Strict multi-position verification feasibility

Selected runtime remains `b1ef257a`; evidence base is `5bbaa110`. This folder contains a new
unselected scorer and offline proposal analysis, not an accepted speculative decoder or speedup.

The system-specific hypothesis is to use earlier candidates' public token completions as proposals
for later candidates on the same prompt. Every proposed token must be verified by the current
candidate's own strict model. Old KV, activations, logits and weights are never reused across
candidates. This follows the proposal/verification separation used by
[vLLM speculative decoding](https://docs.vllm.ai/en/latest/features/speculative_decoding/);
that documentation is context, not evidence of speed or strict arithmetic for this prototype.

First, inspect actual traces rather than assume nearby candidates produce the same text. The
selected strict short trace has only 1/8 identical rows for each of canonical seed 7001's signs;
common prefixes total 75/256 tokens for plus and 106/256 for minus. In the longer vendor chat
control, none of the 64 complete rows are identical to parent for any of eight candidates. These
vendor traces must not be labeled strict results. Whole-parent completion replay is not supported
by this observation.

The offline suffix proposer instead finds the current verified output suffix (2–8 tokens) in an
earlier completion and proposes up to block-size minus one following tokens. Longest suffix wins;
later prior matches overwrite earlier matches. The simulated verifier reads the recorded target
trace, emits only the matching prefix plus one target bonus token, and begins after the first
prefill-selected token. The parent bank contains only parent outputs; the previous bank contains
only already completed earlier candidates. It never contains the current or a later target trace.
Three CPU tests cover no match, a wrong proposed tail and end-of-output handling.

| Trace / proposal bank | Block | Verified emitted tokens per simulated round | Query expansion |
| --- | ---: | ---: | ---: |
| Strict short / parent | 2 | 1.333 | 1.060 |
| Strict short / parent | 4 | 1.575 | 1.206 |
| Strict short / previous | 4 | 1.595 | 1.236 |
| Vendor chat / parent | 2 | 1.289 | 1.138 |
| Vendor chat / parent | 4 | 1.477 | 1.463 |
| Vendor chat / previous | 2 | 1.412 | 1.164 |
| Vendor chat / previous | 4 | 1.735 | 1.544 |
| Vendor chat / previous | 8 | 1.913 | 2.377 |

These are offline counts, not emitted-token throughput or a speedup prediction. Ragged batch
progress, scorer cost, extra model work, prefill and CPU proposal cost still matter.

`BlockVerifier` implements a finite fixed-prefix scorer using the existing B22 projections and
strict nonlinear operators. Each query's key range ends at its own hypothetical position, so later
guesses never enter earlier prefixes. All block positions write unique current-candidate KV slots.
The FP16 model remains primary; a CPU canonical model is used only for the two tiny-layout tests.
The helper holds the engine lock, checks stream and candidate pointer/version identity, uses the
conservative existing graph/workspace budget, and clears request buffers on exit. It supports up
to four positions and 128 total query rows. It is not complete lifecycle qualification.

Two GPU tests pass (Qwen2 and wider-head Llama layouts), checking every position against the CPU
integer decoder through changed guesses, changed weights and restore. Both deliberate future-query
leakage and wrong-sequence-cache mutants are killed on a scratch copy. The trained Qwen pilot also
compares every logit bit at every position with packed one-token-at-a-time scoring. It uses one
FP16 trained model, random prompts/tokens from seed 1949, ten interleaved GPU event samples and
fixed prefixes. No proposal or acceptance loop is executed in this benchmark.

| Batch / prefix length | One position ms | Two positions ms / relative cost | Four positions ms / relative cost |
| --- | ---: | ---: | ---: |
| 1 / 32 | 3.077 | 3.042 / 0.989 | 3.072 / 0.998 |
| 1 / 128 | 3.714 | 3.677 / 0.990 | 3.695 / 0.995 |
| 8 / 32 | 3.133 | 3.416 / 1.091 | 4.679 / 1.494 |
| 8 / 128 | 3.769 | 4.127 / 1.095 | 5.719 / 1.517 |
| 32 / 32 | 4.708 | 7.459 / 1.584 | 12.991 / 2.759 |
| 32 / 128 | 5.762 | 9.418 / 1.634 | 15.975 / 2.772 |

Peak allocated memory across the three scorers sharing one model is 2.811 GiB for batch 32 and
1.412 GiB in the batch 1/8 process; allocator peaks do not prove all resource bounds.

The full batch-32 cost discourages a fixed-block implementation there. Small batches justify a
finite end-to-end experiment: batch 1 can score several positions at similar cost; batch 8 can
score two positions for about 9–10% extra. This is a ceiling observation, not achieved acceleration.
The scorer uses stateless greedy argmax with penalty one; it does not implement EOS, rejection,
advancing cache lengths, repetition penalties or candidate-history storage.

Next experiment: a bounded small-batch proposal/verification loop, compared with ordinary B22 on
fresh canonical candidates and real prompts, including bad/no proposals. Keep current-candidate KV
only, commit only verified prefixes, and clear state on candidate boundaries. Invalid arithmetic in
an unaccepted speculative branch must trigger a fresh strict one-position fallback, rather than
incorrectly failing a candidate whose true path is valid. Infrastructure errors still fail normally.
Tokens must be independent of proposal contents and worker-specific proposal history. Fixed scorer
graphs currently reserve only their initial prefix length; an advancing loop must reserve maximum
context scratch before capture. No managed integration until these conditions have actual tests.

Final harnesses are in `harness/`. Use isolated Python and
`PYTHONPATH=runtime/src:runtime/tests/eval:<folder>/harness` for tests, explicit
`HETEROES_GPU_ACCEPTANCE=1`, and benchmark `--gpu`. The `-01` scorer receipt uses the original
batch-32 harness snapshot; `-02` adds explicit batch selection. Build identities, raw event samples
and peak allocator measurements remain in the JSON receipts.

## What this does NOT show

An end-to-end speculative decoder, emitted-token speedup, near-vLLM strict kernel performance,
cross-GPU or native Windows acceptance, arbitrary candidate/proposal invariance, complete error or
resource qualification, managed operation, quality or learning. No full secondary inference model,
quantized primary replacement, remote GPU compute, push, merge or deployment occurred.
