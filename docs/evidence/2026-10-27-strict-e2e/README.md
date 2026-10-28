# End-to-end strict runs on two GPUs, a worker fault and a 600-generation soak (2026-10-27)

Branch `work/final-2026-10-27`; the plain and fault runs used the runtime source of `45b42439` (probe changes later
committed in `f77c7225`), the soak `012acebf`. Probe: `acceptance/probes/strict_e2e.py` (registered as `strict-e2e`, profile `faults`, gate
`M5.end-to-end`). CPU coordinator (`python -m heteroes.v3 serve --device cpu`) on this machine; workers on the local
RTX 5070 Ti (SM120, Linux) and Thảo's RTX 3060 (SM86, WSL2, over Tailscale, source from `git archive HEAD`).
Recipe v3 `strict_b22_v1`, trained Qwen2.5-0.5B, `acceptance/e2e/arith96.jsonl`, 8 candidates, 16 rows, 32 tokens,
audit rate 0.5. The lab and its device states were not used. Numbers below: `python3 summarize.py`.

| Run | Generations | Results 5070 Ti / 3060 | Cross-GPU audits matched | Other |
| --- | --- | --- | --- | --- |
| `plain/` | 4 | 31 / 1 | 14 / 14 | one update changed the weights |
| `fault/` (`--kill-local-at 2`) | 4 | 27 / 5 | 14 / 14 | local worker SIGKILLed while holding a lease, restarted 30 s later; 1 lease expired and was redone |
| `soak/` (`--generations 600`, weights `layers.23.self_attn.o_proj`) | 600 | 3228 / 1572 | 2371 / 2371 | 6 updates changed the weights |

- Every run: the stored texts re-score to the committed rewards, and the recorded updates replayed on a fresh CPU model
  give every published child hash.
- The fault run gave the **same four children and generation record hashes** as the plain run, although the
  candidates went to the two GPUs in a different split.
- Soak coordinator bookkeeping per generation (early / middle / late thirds): record 4.6 / 4.8 / 4.5 ms, update
  8.1 / 7.9 / 7.6 ms, publish 1.0 / 0.9 / 0.9 ms, whole generation 1.03 / 0.99 / 0.98 s (median 0.96 s, max 18.3 s,
  the first generation with model warm-up). No growth over 600 generations.
- The first try (not kept) passed trivially: the fixture's answers were strings, every reward was 0 and no update
  happened. Fixed in `f77c7225`; the probe now fails when no update changed the weights.

## What this does NOT show

- Not a lab run: the managed product runner, its recovery points, uploads and the lab's device states were not used,
  so this does not measure the product's recovery-point bookkeeping (gate `M3.bookkeeping` stays open).
- Not learning: rewards stay near their start (sigma 0.001, few weight changes); the soak trains one 896x896 matrix to
  keep the published weights small (disk). Only two GPU models and one model; native Windows was not in these runs.
- Not a throughput measurement; the 3060 got fewer candidates because the scheduler favours the faster GPU.
- The `recordHashes` of the plain and fault reports were added afterwards from their `summaries.json` (the field came
  with `--compare`); the children were in the reports from the start.
