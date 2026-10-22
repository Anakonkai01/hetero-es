# Candidate13: real-user fixes (2026-10-22)

Branch `feat/real-user-c13` (from `feat/gsm8k-demo` 3663531). Build `lf1-20261022-r11-candidate13`, deployed commit
`948059b` (lab, 5070ti-nhan and 5070ti-nhut agents, installers). Scope set by the owner in a grill on 2026-10-22 ~16:30
(memory `hetero-es-real-user-c13-2026-10-22`, plan `~/.claude/plans/pasted-content-id-583c-tier-3-enchanted-volcano.md`).

## What changed

| Commit | Change |
|---|---|
| `9423d16` | Finding 9: a member added back is logged `worker_joined` (`rejoin`). Finding 11: a member silent for 2 min is logged `worker_unreachable` (and `worker_reachable` when back), the live view shows it lost |
| `372775a` | Devices: the owner or an administrator renames a device on the web; Delete revokes and removes in one step, never while a run holds the device |
| `0948b6b` | No Tailscale by default: a small dataset file (signed, at most 64 MiB) uploads over the lab's public address with its own Caddy body limit; `doctor`/`setup` no longer assume Tailscale |
| `6ed92d3` | Python sampler `python@1:<sha>`: runs on the coordinator, pinned like a scorer; workers, audits and the verifier take the frozen rows from the generation context |
| `f88fbc3` | `heteroes.sdk_lab`: Lab/Model/Dataset/Run, hub models as REFERENCE, rows from any loader, cell-written functions frozen from their own source, devices qualified before the experiment, batch and chunks suggested from per-GPU memory measured at model qualification (`product/chunk_memory.py`) |
| `bd2a114` | Create page leads with the notebook (example, notebook and SDK wheel served at `/notebooks/`); `runtime/notebooks/researcher.ipynb` |
| `a49cd93` | Check fixes (duplicate translation keys, shared runtime module, no pinned id outside the catalog) |

The ledger module and the GSM8K demo evidence are unchanged (`052d87e` reverted an accidental edit of both);
`verify_managed_run.py` here is the demo verifier plus a Python sampler's frozen rows.

## Checks

`checks/`: all PASS after `a49cd93` except `runtime-tests` (3 demo tests need matplotlib, absent from the check
interpreter, as in wave 1). Mutation checks on scratch copies: findings 9/11 5/5, devices 5/5, sampler 7/7, notebook→lab
11/11 killed (one survivor fixed with a test).

## Deploy (`deploy-lab-c13.log`)

17:58 by the owner from a terminal (the permission classifier refuses stopping the live lab). Database copy at the stop:
`/mnt/Archive-2tb/heteroes-local/backups/candidate13-20261022/`. The script stopped at its last check (`curl -I` gets
405: the lab answers GET only); the notebook and wheel answer 200 and the installers were published afterwards
(`installers-*-c13.json`). Agents: `update-c13-*.log`, runtime `08411835bac0`, self-test PASS.

## Chunk 128 (`chunk128/`, `chunk_probe.py`)

128 GSM8K train rows, FP32, 2 candidates × ±σ (512 texts per chunk per GPU): **every text equal** at chunks 16, 64 and
128 on the RTX 5070 Ti and the RTX 3060 (WSL, the workers' runtime copied over the LAN; removed afterwards). Seconds per
candidate: 5070 Ti 24.3 / 14.2 / 13.5, 3060 75.5 / 42.8 / 40.4. Chunk 128 is **not** added to `EXACT_CHUNKS`: it gains
about 5 % over 64 and the 1660S (Turing) was not probed.

## Acceptance

1. **A new machine without Tailscale.** 5070ti-nhut: new outbound connections of the worker's user to 100.64.0.0/10
   rejected (iptables owner match; inbound SSH unaffected), `uninstall`, then the public one-line install from the lab,
   `setup` with a pairing code: paired as `cli-34312a79fbbc`, approved, ON, `doctor` network ok.
2. **A real run from the notebook** (`notebook-run/`): RESULTS BELOW.
3. **The owner tries the web**: rename, delete (the old revoked `5070ti` and `5070ti-nhut` devices are left for it),
   live view.

## What this does NOT show

- Windows: the 3060-thao app is still the candidate9/12 one; the Windows installer of this build is untested.
- A machine that never had Tailscale: 5070ti-nhut has it installed; only its worker's new connections into the tailnet
  are refused.
- Chunk memory measurement and suggestions on any GPU but those that qualify during the acceptance run.
- The 1660S (offline since 13:40, hardware) runs nothing of this build.
- Learning: the acceptance run is 5 generations of 8 candidates.
