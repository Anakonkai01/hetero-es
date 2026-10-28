# Integration validation — 2026-10-10

The agreed private deployment works with the RTX 5070 Ti and Quang's RTX 3060.
Both repositories remain on their separate local integration branches. No push,
merge, release tag, public deployment or machine autostart was performed.

| Check | Observed result |
| --- | --- |
| Track A full CPU suite | 2,138 passed, 21 skipped, 74.77 s |
| Track B backend | 15 passed; one Starlette/httpx deprecation warning |
| Frontend build and lint | Passed |
| Explicit mock demo | 22 behavior groups passed |
| Real browser workflow | Login, workspace, rewards, exact seed, worker inventory, role isolation, create/start/cancel and checkpoint preservation passed |
| Browser observation of the two-GPU run | Actual completed results and authenticated summary download passed; no JavaScript errors |
| Required two-GPU recipe | N=8, G=3; 24 accepted candidates and 3 applied/published updates |
| Safe cancellation | Stopped after one complete generation, retained its checkpoint |
| Coordinator failure | One injected owned-process SIGKILL after generation one; recovered once and completed generation three |
| FIFO and queued cancellation | Next run started after pool release; a cancelled queued run never launched in Track A |
| Offline selected-worker fallback | Continued on the selected 5070 Ti when the selected 3060 was unavailable |

The skipped Track A cases require opt-in model/environment flags; they are not
claimed as exercised by the CPU suite. GPU campaigns below exercise the real
pinned model independently. Cancellation and owner privacy tests were also
checked against deliberately broken implementations in disposable copies;
the corresponding tests failed. The WSL library-selection tests were observed
failing before their fix and passing afterward.

## Required hardware run

Run ID: `c982ec016aaa43b592457ef9bfba9423`, status `COMPLETED`.

- Pinned Qwen2.5-0.5B-Instruct revision:
  `7ae557604adf67be50417f59c2c2f167def9a775`.
- `arith16`, `hf_generate`, FP32 evaluation, canonical CPU noise,
  alpha=sigma=0.001, greedy synchronous dispatch.
- Accepted results: **17 on 5070 Ti, 7 on Quang's 3060**. Counts come from the
  committed `result` rows joined to their winning `attempt` rows.
- Both workers passed the same recipe self-tests and verified update replay
  at the two subsequent generation boundaries. Both exited normally and their
  shutdown was confirmed before the pool was released.
- Downloaded checkpoint SHA-256:
  `050aaf5f0abe4b8840bd671e2836a51149c2070cd8e22a4b890f8d32a7bbf3ae`.
- The acceptance script took 58.24 s including download verification.

Quang's WSL machine had a Linux NVIDIA 580 library alongside the mounted
Windows driver. CUDA initialization failed with the default library selection.
Selecting `/usr/lib/wsl/lib` plus the matching Windows PTX JIT directory made
both a CUDA tensor allocation and the actual worker campaign pass. The helper
now makes that selection per process, without changing drivers or the existing
virtual environment. NVIDIA's [WSL guidance](https://docs.nvidia.com/cuda/archive/13.2.0/wsl-user-guide/index.html)
explains the Windows-driver library mapping; a [CUDA samples issue](https://github.com/NVIDIA/cuda-samples/issues/433)
reports a similar CUDA 13.2 initialization crash. Our local acceptance is the
evidence for this deployment's fix.

The optional 1660S remained unreachable by SSH. It is reported offline and was
not admitted or counted toward the required acceptance. Two earlier attempts
with the 3060 selected completed using only the 5070 Ti; these are retained as
fallback evidence and are not classified as successful two-GPU runs.

## Cancellation and recovery

Browser cancellation run: `6ab71164869548c3b9cbbc915cb5437d`.
It preserved one complete generation and a downloadable checkpoint.

Recovery run: `b04ed35bbe634d8683487cd2d0404993`.
It recovered once using the same run ID/configuration/ledger and completed all
three generations. Download SHA-256:
`e9846aa00db2013ec603ac462a91df99377e408134493772140e7b49f87f900e`.
FIFO successor: `24c8202c980644e687149c93f00884a3`.
Queued cancellation: `ba124f6fed6247f1b7791be27c8b8c0e`.

This is evidence for integration correctness, not learning efficacy, scheduler
speedup, automatic performance admission, multi-host backend availability or
power-loss durability. Coordinator storage remains a single-host dependency.
Timestamps originate from each host; cross-host clock synchronization is not
assumed. Unknown remote shutdown deliberately keeps the pool reserved.

## Evidence locations

Sanitized summary in Track A:
`artifacts/experiments/2026-10-10-track-b-integration/validation.json`.
Original runtime ledgers, event logs, weights and service logs are outside git:
`~/.local/share/heteroes-integration/`.

Product acceptance files: `product/two-gpu-evidence.json`,
`product/recovery-evidence.json`, `product/browser-evidence/acceptance.json`
and `product/browser-evidence/observation.json`. Browser screenshots include
`completed-runtime.png`, `cancelled-runtime.png` and `worker-inventory.png`.
Tokens, password values, SSH material and raw ledgers are not committed.

Across nine managed runtime runs, a conservative bound charging every selected
GPU for the entire supervisor run lifetime is **0.177 GPU-hours**, below the
agreed 2 GPU-hour budget. This includes preparation, shutdown and selected
workers that never started; it is not a measured utilization integral.
