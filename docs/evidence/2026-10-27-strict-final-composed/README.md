# Final bounded performance round: three exact routes composed, 2026-10-27

Owner decision (Claude session, 2026-10-27): one last bounded round. Compose the three unselected positive pilots,
measure baseline/composed ABAB; promote if short32 gains at least 1.0% with unchanged token hashes, otherwise stop.
Either way the near-80%-of-vLLM goal closes as **not achieved**.

## Whole-generation ABAB (before promotion)

[harness/bench_composed.py](harness/bench_composed.py) loads one engine per process: `baseline` is runtime `0eb86cb9`;
`composed` applies, unchanged from their sealed folders, the TMA host-map prefill transport
(`2026-10-27-strict-tma-host-maps`), request-sized KV slots (`2026-10-27-strict-request-cache-context`) and 128-key
GQA stages (`2026-10-27-strict-attention-key-stages`). [harness/abab.sh](harness/abab.sh) ran B/C/B/C as separate
processes, five timed generations each, on the idle local RTX 5070 Ti. Raw JSON/logs in `raw/`.

| Case | baseline r1 / r2 | composed r1 / r2 | mean gain |
| --- | ---: | ---: | ---: |
| short32 | 9883.5 / 9858.6 | 10082.4 / 10066.7 | **+2.06%** |
| chat128 | 9889.6 / 9878.7 | 9952.3 / 9951.7 | +0.69% |

Token hashes are `bc4a5504…` (short32) and `a9fad5ca…` (chat128) in all eight processes. Short32 rises from 71.3% to
about **72.8%** of the vLLM control 13834.6 token/s. The 80% target (11068 token/s) is **not reached**.

## Promotion into runtime source

The rule (≥ 1.0%, equal tokens) is met, so the three routes are promoted as SM120 execution routes with the same bits:

- `eval/integer_tma.py`: the streamed B22 projection body derived by checked text edits (byte-equal to the measured
  harness kernels except the timeout bit), host tensor-map templates (bounded, address patch only), by-value maps.
  Used for SM120 B22 prefill with more than 128 rows, one K split, 32-row tiles and the `stream` schedule.
- `eval/attention_stages.py`: the 128-key stage kernel, byte-equal to the measured one; it replaces only launches
  where the original would use the GQA kernel.
- `strict_decoder_graph.request_context`: physical KV per owner = longest prompt + new tokens, rounded up to 16, never
  above the configured context. Admission and the memory bound still use the configured context.
- **Transport ABI**: a TMA barrier that never completes sets error bit **8** (the pilot used 4, which collides with the
  decode layout bit). Bit 8 raises `StrictTransportError`, an infrastructure failure, before any arithmetic bit.

Each route can be switched off on a kernels object (`prefill_tma`, `attention_key_tile = 0`) for comparisons.

## Checks so far

- New tests: `tests/eval/test_integer_tma.py` (50), `test_attention_key_stages.py` (45), `test_request_context.py` (12):
  107 pass on the 5070 Ti (`HETEROES_GPU_ACCEPTANCE=1`); 23 of them are CPU tests.
- Mutation: [checks/mutation-01.log](checks/mutation-01.log), **14 of 14 mutants killed**
  ([harness/mutants-01.json](harness/mutants-01.json), also registered as `acceptance/mutants/strict-routes.json`).
- Found while testing: the original GQA decode launch fails with `CUDA_ERROR_INVALID_VALUE` for 692–693 keys, because
  `gqa_attention_eligible` ignores the kernel's static shared memory. It is a loud failure, not a wrong result, and
  is not changed here; the stage route covers those contexts on SM120.

Full GPU suites, trained parity on three hosts, throughput floors and packaging follow through `scripts/accept.py` and
are recorded in `docs/acceptance/`.

## What this does NOT show

Not a near-80% result, not a cross-host speed claim (the routes are SM120-only; SM86 only gets the request-sized KV),
not qualification for arbitrary models or inputs. No learning, deployment or lab-state change.
