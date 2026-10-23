# 2026-10-22 ~21:30: finding 13 diagnosed; noise engine v2 designed (prototype only); handoff to Codex

Branch `feat/real-user-c13` (not pushed). Lab on `2047452`, agents on candidate13b, all idle. Nothing in
`runtime/src` was changed this session; the v2 prototype is in `docs/evidence/2026-10-22-finding13-libm/prototype/`.

## Finding 13: cause (proved), evidence `docs/evidence/2026-10-22-finding13-libm/README.md`

- The CPU noise engine `numpy_pcg64_normal_f32_to_f16_v1` calls the **host libm `log1pf`** in numpy's ziggurat tail
  (|x| > 3.654). glibc 2.43 (nhan, Ubuntu 26.04, correctly rounded) and glibc 2.39 (nhut, Ubuntu 24.04) differ by
  1 ulp in 7.3 % of inputs. That is rarely visible after the fp16 cast, but sometimes the value sits on an fp16
  rounding boundary (`-4.349609` → `-4.348` vs `-4.35`). At g7→g8 one weight of `layers.9.mlp.down_proj` then
  differed, so the hash differed. The coordinator chain is correct (ledger replay on nhan: 10/10 equal). The noise
  self-test (5 golden chunks) cannot see it. Windows/WSL libm were not probed.
- Second defect: after `ReplayFailed` a public-only worker cannot fall back to sync (`bulk_unavailable` → exit
  `needs_private_route`). The agent restarts it 6 times, and every restart fails the same way.

## Owner decisions (2026-10-22, in chat)

1. **Build noise engine v2 that does not use the system libm** ("làm hẳn thằng 2"). This approves adding an engine in
   `runtime/src/heteroes/noise` + the plumbing in `es/`. v1 must stay bit-identical (golden fingerprints unchanged).
   No temporary log1pf blocker.
2. **Restart loop: stop it and show the reason** (no restart after `needs_private_route`; live view/device table say
   why). The owner says this is **TEMPORARY**: they will look for a real solution later (e.g. recovery over the public
   route).
3. **Still open, asked at the end:** the owner had thought noise was made by CUDA. Answer given: the CUDA engine
   (`torch_cuda_philox_chunked_f32_to_f16_v1`, G7) exists but the lab only accepts `noiseEngine: "cpu"`
   (`v3/lab_cli.py:78`). It needs a GPU on the coordinator and depends on CUDA's maths library (same risk class).
   Options put to the owner: (A) finish CPU v2 (recommended), (B) enable the CUDA engine in the lab, (C) A then B.
   **Ask the owner which one before writing the code.**

## Engine v2 design (prototype `prototype/proto_v4.py` + `prototype/gen_table.py`, measured)

- Same chunk addressing as v1 (`ChunkNoiseAddress`, 2^18 elements, SHA-256 seed with the NEW version string, e.g.
  `pcg64_u32_to_f16_normal_quantile_v2`), `PCG64(seed).random_raw(ceil(n/2))` viewed as little-endian uint32
  (`astype("<u8").view("<u4")[:n]`).
- Word w: sign = w >> 31, u = w & 0x7FFFFFFF. Value = the positive fp16 whose bit pattern i is the number of
  thresholds T_i ≤ u, where `T_i = floor(2^31 · erf(m_i/√2))` and m_i is the midpoint of the fp16 values with bits i
  and i+1. Output bits = i | sign<<15. This is an exact N(0,1) rounded to fp16, with tails up to 6.23. **Integer
  operations only**, so it is identical on every CPU/OS (and portable to a GPU later).
- The table (17,980 entries) is computed with `decimal` (60 digits, positive-term series for erf, correctly rounded
  exp/sqrt) in about 0.5 s. Minimum distance to an integer is 5.8e-5, so the floor is unambiguous. Non-.py files do
  NOT reach the runtime or wheel, so either compute it lazily at first use (thread lock) and pin its SHA-256, or embed
  it as a generated .py.
- Fast path: 2^16-bucket table `LO` (uint16, bit 15 = bucket holds ≥ 2 thresholds, 1.7 % of buckets);
  `idx = lo + (u >= T[lo])`, with `searchsorted` only for flagged buckets. Process in blocks of 131072.
  Equal to plain `searchsorted` on the tested chunks. Speed per 2^18 chunk (14700KF): single 0.8-1.6 ms (v1 ~2 ms);
  4 threads 0.32 vs v1 0.51; 8 threads 0.22 vs 0.27; 16 threads (the default max) 0.30 vs 0.165 ms. Statistics on
  20M samples: std 0.99998, kurtosis 2.9992.

## Plumbing (call sites found; default stays v1)

- `noise/contracts.py`: add the v2 version string to `KNOWN_ENGINES`. New `noise/engine_v2.py` (+ golden chunks and
  fingerprint). `engine.iter_parameter_noise_chunks(..., generate=...)`; `es/perturb.py` `perturb_model_` and
  `es/update.py` `apply_coefficients_`/`apply_es_update_`/`_apply_coefficients` get `engine=ENGINE_VERSION`.
- Pass `engine=recipe.engine_version` at: `executor.py:223` and `_apply_record`, `coordinator.py:353`,
  `v3/evaluation.py:239`, `profile_setup.noise_ops`/`_cpu`, `worker_runtime.py:252`, `product/qualification_v3.py:209`,
  `product/cpu_coordinator.py:38`; `model/loading.check_recipe_selftest` + `build_recipe`; `v3/run.build_documents`
  (`"cpu"` → v2 for new runs, v1 stays readable); `manifest.py` validation.
- Devices: `product/selftest.py` reports `noiseVersion` v1 only; `backend/device_models.py:41` is
  `Literal[v1]`. Add a list of supported engines (self-test both), and have the lab schedule a v2 run only on devices
  that report v2. Old 13b agents reject an unknown engine (`v3/documents.py` `KNOWN_ENGINES`), so it fails loudly.
- Then: tests first (v1 golden unchanged, v2 golden, v2 == searchsorted reference, cross-check on nhut glibc 2.39 =
  nhan 2.43, CPU-only), mutation check, end-to-end update/perturb timing, candidate14 build/installers/lab deploy,
  run with replay on nhut. Windows (3060-thao) still needs someone at the screen.

## State to know

- `~/f13-diag` on nhut (heheboiz@100.108.195.50, SSH allowed by the owner for finding 13) holds a ledger copy and the
  diagnostic scripts (~2 MB); delete it when done.
- nhut still has the iptables "no Tailscale" rule (see `handoff-2026-10-22-candidate13-close.md`).
- Lab session token in `~/.config/heteroes-demo/session.json` expires ~06:00 on 10-23.
- Still open from before: chunk 128 decision, push/merge of `feat/real-user-c13`, Windows app on 3060-thao.
