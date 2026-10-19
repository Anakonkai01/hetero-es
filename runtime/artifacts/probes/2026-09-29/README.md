# Physical probe evidence — 2026-09-29

Raw outputs of the cross-machine compatibility and NoiseEngine probes, copied **byte-for-byte** (verified with `cmp`) from `~/projects/heteroes-test/` on the 5070 Ti machine on 2026-09-30. Do not edit these files; add new evidence in a new dated folder.

Not copied: the checkpoints `qwen_es_milestone1_gen1/` and `qwen_es_milestone2_final/` (large weights stay out of Git).

## Machines

| Host | GPU | Environment used |
|---|---|---|
| `5070ti` | RTX 5070 Ti, 16 GB, cc 12.0 | `ai` (torch 2.10.0+cu128, Transformers 5.5.0, Python 3.12.13) for `probe_5070ti.json`; `heteroes-match` (torch 2.13.0+cu132, Transformers 5.17.0, Python 3.12.14, NumPy 2.5.3) for everything else |
| `heteroes-worker-1660s` | GTX 1660 Super, 6 GB, cc 7.5 | `.venv` (torch 2.13.0+cu132, Transformers 5.17.0, Python 3.14.4, NumPy 2.5.2) |

Both: Linux 7.0.0-34-generic x86_64, glibc 2.43, NVIDIA driver 595.91.07, model `Qwen/Qwen2.5-0.5B-Instruct` @ `7ae557604adf67be50417f59c2c2f167def9a775`, FP16.

## Files

| File | Produced by | What it shows |
|---|---|---|
| `heteroes_compat_probe.py` | — | Compatibility probe script (CUDA-RNG perturbation, evaluation, restore) |
| `heteroes_noiseengine_probe.py` | — | Canonical NoiseEngine v1 probe script |
| `probe_5070ti.json` | compat probe, `ai` env | 5070 Ti, unmatched runtime |
| `probe_1660s.json` | compat probe | 1660S |
| `comparison.json` | compat compare | **Unmatched** runtimes: noise DIFF, candidate predictions DIFF, restore exact on both |
| `probe_5070ti_matched.json` | compat probe, `heteroes-match` env | 5070 Ti with runtime matched to the 1660S |
| `comparison_matched.json` | compat compare | **Matched** runtimes: same outcome as unmatched |
| `noiseengine_5070ti.json`, `noiseengine_1660s.json` | NoiseEngine probe, sampled | Same global hash on both |
| `noiseengine_5070ti_full.json`, `noiseengine_1660s_full.json` | NoiseEngine probe, `--full` | Same bytes for all 290 tensors / 2,105 chunks |
| `milestone2_history.json` | notebook `run_es_generation` | Three-generation log (fixed seeds `[0..3]`); machine not recorded in the file |

## SHA-256 checksums

```text
abc81cf697dd358d989285509f6e51abcd2be28af9b746d5a4ef535138419fce  comparison.json
4f8e5ddd07a5ad27a8a74a1ab55f57876403b9a46a6f61df3dbfb663ec4e3fbc  comparison_matched.json
db6bbae6e0621af2ad6a3770004b18e5a6cdface69a1839f877c05180f90ef73  heteroes_compat_probe.py
dd9cd0ac7cee9227e1a85ca0bfb5e2afdc9042eaaf8f72a1f820a3bf90a8dff1  heteroes_noiseengine_probe.py
ff912b1283398fb03345f2ca02c24e7ea4636e16ef3fcc427d0d8a33c070c446  milestone2_history.json
8f4eef9d7035ce96ecaa79275f54df65dd8dea3b680d5a54783bbdcf42d20600  noiseengine_1660s_full.json
696ac74d992a94cc23d547d7d9b6714683025544088bbd78a2e13344a902b83d  noiseengine_1660s.json
b91b5a4197aeba8d060be52ca91198154211087f6bf10f84ab66c02c82a3fdb7  noiseengine_5070ti_full.json
703895aa563da083c0471154152517233353ed4a70efb059273cda497a83ac69  noiseengine_5070ti.json
34be18e8ca6a7230fb69c5c40dee96a93788193459531eaa53ae18fdc3dc81ed  probe_1660s.json
0d35efca4ddc097955e63faf3fdb646bd348958c831b7dae7609ea9671252721  probe_5070ti.json
c87ec6873c7ef8e7d759e505a0d3cdd4cdabcb6dd30f629e830336971b2b6311  probe_5070ti_matched.json
```

Verify with `sha256sum -c` after pasting the block above into a file, or compare by eye with `sha256sum *`.
