# vLLM feasibility probe (2026-10-20)

Outcome: vLLM can load changed Qwen weights in place and restore every parameter exactly, but it is **not integrated** as
a HeteroES decoder. The final FP32 probe differs from HF on 3/64 perturbed texts; no automatic equivalence or ES throughput
claim is justified by this small test. Existing HF decoders remain the runtime choices.

## Setup and receipts

Owner-authorized RTX 5070 Ti, pinned Qwen2.5-0.5B-Instruct (`7ae55760…`), 64 synthetic multiplication prompts (16 ask for
steps, 48 ask for an integer), 64 new tokens, chunk 64. The base model and one canonical seed-20261020 perturbation
(sigma 0.01) are evaluated. `probe-final.py` is the final harness; raw outputs and environment reports are retained.

An isolated `.scratch/vllm-probe/venv` was installed using the `uv` executable, without installing into Conda `ai` or
`heteroes-match`. It contains vLLM 0.32.0, Torch 2.13.0+cu130 and Transformers 5.19.0 (`packages.txt`, install/resolution
logs). These follow the [vLLM release](https://github.com/vllm-project/vllm/releases/tag/v0.32.0) and
[published package metadata](https://pypi.org/project/vllm/0.32.0/). FP32 uses FLEX_ATTENTION, eager execution, disabled
prefix caching and 45% GPU memory allocation. Function RPC is enabled only in this private probe with
`VLLM_ALLOW_INSECURE_SERIALIZATION=1`; this is not a product or network-service setting.

- Attempt 1 started the engine, but its function RPC correctly refused serialization without that explicit setting.
- Attempt 2 exposed `save_model` choosing the tied `lm_head` alias; vLLM refused a checkpoint lacking its embedding key.
- Attempt 3 saves unique canonical HF parameters and restores exactly, but omits HF's repetition penalty. Its text
  differences are **not** parity evidence. `probe-attempt1-2.py` and `probe-attempt3.py` retain those exact harness versions.
- **Attempt 4** reproduces HF repetition penalty 1.1 and both EOS IDs. After every changed/base reload it compares all
  **170 packed vLLM parameters** to their exact HF source tensors, including concatenated QKV and gate/up projections.
  Every check passes. The restored vLLM parameter fingerprint and texts equal its initial fingerprint/texts.
- `pinned-hf.json` repeats HF on the project's Torch 2.13.0+cu132 / Transformers 5.17.0 stack: parent/perturbed FP16 weight
  hashes and all base/perturbed HF texts match the isolated vLLM environment. The measured HF/vLLM differences are not
  explained by those two HF environments. `summary.json` is the compact comparison.

## Measurements

Three timed repetitions after warmup; initialization excluded. Each cell has 64 prompts.

| Cell | HF median | vLLM median | Decode ratio | Different texts |
| --- | ---: | ---: | ---: | ---: |
| Base | 0.888 s | 0.682 s | 1.30x | 0/64 |
| Perturbed | 0.902 s | 0.712 s | 1.27x | 3/64 |

Checked changed/base reloads take 1.371/1.378 s. These timings include file reads, in-place loading, synchronization,
every-parameter comparison and RPC; they are **not raw weight-copy times**. The checked reload overhead exceeds the
decode saving in this particular short probe. An end-to-end ES implementation could have different costs and needs its
own evidence. No new decoder name, recipe behavior, model qualification or deployment is introduced here.

## What this does NOT show

- No text parity guarantee, learning benefit, fair end-to-end ES speedup, long GSM8K benchmark or cross-3060 qualification.
- No characterization of all vLLM backends, half precision, LoRA, newer versions, other models or longer workloads.
- Timings come from three repeats and a small synthetic workload; they are not confidence intervals.
- Generated weight artifacts live on the verified Archive disk; private ledgers and runtimes remain on the system disk.
  The disposable 7.9 GB probe environment may be removed after freezing these receipts; reinstall from the pinned versions
  for another probe. Source environments are unchanged.
