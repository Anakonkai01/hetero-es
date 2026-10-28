# GTX 1660 SUPER candidate6 qualification (predeclared)

Predeclared 2026-10-21 before running. Owner approved this the same morning while both 3060 machines were
unreachable and the 50-generation acceptance was postponed to the evening (more machines may join).

Machine: `anakonkai@heteroes-worker-1660s` (Tailscale 100.119.83.46), Ubuntu 26.04.1 native Linux,
GTX 1660 SUPER 6 GiB (Turing, compute capability 7.5), driver 595.91.07, 16 CPU threads, 45 GiB RAM,
211 GB free on `/`. This architecture has not been checked with the FP32 + CPU-guard decoder before.

## Steps

1. Install the candidate6 CLI Worker with the unchanged private `install-worker.sh` from the 5070's private
   tailnet HTTP server (build `lf1-20261020-r11-candidate6`, bundle SHA256
   `c0a153447df745d28c42e0b0c8ae1e46d5387d1631e0825d3f3725cbd9b8717a`) into a fresh
   `~/.local/share/heteroes-worker`. Nothing else on the machine is removed. Expected runtime directory
   `aa74bad820b9`; installed `cpu_guard.py` SHA256 must be
   `150ac9fdd1464e6cdb41bbc624173de28f01f53019a04f18b77e178ceb2ea95d`.
2. `HETEROES_GPU_ACCEPTANCE=1 heteroes-worker selftest --device cuda`. PASS required.
3. Run the unchanged nine-case probe (`../2026-10-20-fp32-cpu-decoder/product_gpu_probe_final.py`) through
   the installed Python/source and the packaged `worker_environment()`, on the SHA256-verified generation-10
   parent (`dfbfa65c...a93d9`) and the same public inputs. No lab, lease or access token involved.

PASS for step 3: for all nine evaluations, full new-token arrays, completion texts/hashes, input IDs/masks,
perturbed FP16 and evaluation FP32 weight hashes equal the committed 5070 final probe results, and the
parent is restored exactly after each. Any difference is recorded as a mismatch and is NOT retried away;
the 1660S would then stay out of tonight's run until explained.

## What this does NOT show

Not the managed 50-generation acceptance, outage/retry or audit evidence, and not a universal numerical
bound. The 1660S has a history of an unstable PCIe link; a crash or disconnect is recorded as a hardware
event. No join/approval in any lab, no public/live change, no merge or release.
