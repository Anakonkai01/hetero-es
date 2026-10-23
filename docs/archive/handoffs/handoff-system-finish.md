# Handoff — system finish: researcher journey on an isolated r11 lab (2026-10-20)

For the next agent (Codex or Claude). Read `../AGENTS.md` first, especially **Project claim**: HeteroES claims a
system, not that ES learns; learning runs are parked. Talk to the owner in Vietnamese, simply. Branch
**feat/v3-audit-recovery**; nothing pushed, deployed or published; the live lab (r10) and its devices are untouched.
Approved plan (Claude): `~/.claude/plans/h-y-ti-p-nh-n-ti-p-encapsulated-adleman.md`. It is summarized below so you do not
need it.

## Owner decisions (2026-10-20)

- Finish the whole system: A r11 release, B real multi-machine run, C faster decoding (hf_compact into v3, measure
  vLLM), D researcher features. **Recipe formats may change freely if correctness and replay hold** (new versioned
  names; old names kept so recorded runs replay bit for bit).
- Target flow: a researcher signs up on the web → admin approves → creates a lab (workspace) or asks to join one →
  creates an experiment with their own data/model/sampler/sigma/coefficient rule → runs it on the lab's coordinator and
  workers.
- **Python rewards fully open on the web lab** (reverses ADR-008 decision 4 for managed runs). Record it in ADR-008 and
  `docs/SECURITY-NOTES.md`; non-blocking safeguards only (child process with time limit, audit entry). Workers never
  run researcher code.
- Request-to-join a listed lab: **done**. Default coordinator per lab: **done**.
- Datasets well above 3 MB: default 1 GB per file and 10 million rows, platform-admin configurable; store as files with
  streamed SHA-256, workers download and verify.
- **Any machine may be the coordinator** (Windows, small GPU, CPU-only). Today four layers forbid it:
  `desktop/worker/electron/network.cjs:28` `qualified()`, `runtime/src/heteroes/product/qualification_v3.py:233`,
  `qualification.py:176`, `selftest.py:23`, and `backend/device_models.py` (native Windows profiles must be worker-only).
  The update must stay bit-identical. Prove it with the 3060 as coordinator. A Windows coordinator loads the pinned
  adapter file and never makes one. The self-test reports update seconds per generation, and the web shows them.

## Done this session (all tests first; mutation receipts in `evidence/2026-10-20-r11-researcher-journey/mutation/`)

| Commit | What |
| --- | --- |
| c997449 | AGENTS.md "Project claim"; learning items parked |
| 794069c | BUG: managed coordinator launched before its inputs were transferred (KeyError 'datasetPath') |
| aa3ccf9 | BUG: default study cache checked against the models' disk UUID → every managed v3 run failed; failure reason shows our own messages only |
| 204defa | BUG: a run that failed before starting workers never released the GPU (workerAlive None) |
| 823b146 | BUG: device approval offered the admin's workspaces, not the owner's |
| 3a6c440 | managed validation decodes with the recipe's chunk (first validation took ~15 min) |
| 70bef41 | translations: account actions, server waiting/failure reasons, experiment page |
| 6d42bf5 | form: end alpha default alpha/10, device names, review step lists every ES choice |
| 5cede5d | request to join a listed lab |
| 567008a | default coordinator per lab |
| b790463 | pluggable batch sampler `epoch-shuffle@1` (old sampler pinned by recorded indices) — **mutation check still to run** |

Backend 329 passed; runtime v3 155 passed; ledger 1015 passed; web units 81 pass; i18n clean. The full
`scripts/check-all.sh` has NOT been run since these commits. Run it first.

## Isolated lab used for the journey (scratch, still running at hand-off)

- `.scratch/isolated-lab/`: candidate2 Lab Server at `http://100.110.165.40:8790` (`start.sh`, Xvfb, its own XDG dirs,
  storage `/mnt/Archive-2tb/heteroes-local/evidence/isolated-lab-20261020`). Secrets in `secret/` (0600): admin
  `labadmin`, researcher `nhan.research`. `api.py` = tiny API helper; `journey/*.cjs` = Playwright steps;
  `journey/shots/` screenshots; **`journey/frictions.md` = the full list of findings (read it)**.
- `worker5070/`: candidate2 Linux Worker driven through `commands.jsonl` → `results.jsonl` (`start.sh`, `stop.sh`).
  Paired as "5070 Ti (máy của Nhân)", approved into "GSM8K ES lab của Nhân", coordinator-capable. Its installed runtime
  (`xdg/config/@heteroes/worker/runtimes/8f276f5aef04/src`) was patched in scratch with the agent.py/prepare.py fixes
  above. That is a test-only hack; candidate3 must ship them.
- Baseline experiment `9e68c65d77064e9499a92b3c95703cf4` (v3, N=16, 4 generations, cosine sigma, centered-rank,
  cosine alpha, momentum, chunk 64, GSM8K v1) was RUNNING generation 3 at hand-off, coordinator + worker = 5070 Ti.
- To stop everything: `worker5070/stop.sh`, then terminate the server's node/Electron processes by PID (never
  `pkill -f`; see AGENTS.md). The Xvfb of the server is in `server-xvfb.pid`.

## Next steps, in order

1. `scripts/check-all.sh docs/evidence/2026-10-20-system-finish/checks`; mutation check for `v3/data.py` sampler
   (mutants: wrong epoch index, no shuffle, short last batch dropped, default sampler changed).
2. Record the baseline run's result (ledger hashes, timings) in `docs/evidence/2026-10-20-r11-researcher-journey/`.
3. **3060 (owner must power it on; Tailscale was offline all session):** install the Worker (candidate3 when built)
   with data on D:, self-test, pair to the isolated lab, approve into the researcher's workspace, rerun the baseline
   recipe on 5070 Ti + 3060: audits match, final weights equal to the 5070-only run, time per generation 1 vs 2
   machines; then uninstall. SSH `thao_nguyen@100.92.20.58` was authorized by the owner for this work.
4. **Model qualification for a new model** (blocker for "my own model", friction 23): an agent command that runs the
   v3 compatibility probe on a newly registered manifest, a lab-built reference from the first device, the others
   reproduce it, and the lab records the per-device qualified hash. Plus a manifest helper (friction 11:
   `heteroes manifest <dir>` CLI and/or the web computing it from an HF repo id + revision).
5. 2b remainder: Python rewards on the web (upload, freeze, coordinator-only execution), large datasets, any machine as
   coordinator (needs the 3060).
6. Plan steps 3, 4, 6, 7, 8: hf_compact for v3 (+ 5070/3060 probe); vLLM probe in `.scratch/vllm-probe/venv` (uv
   binary from Conda `ai`, no env changes); `heteroes eval` (Pass@K, majority) and `heteroes compare` (McNemar,
   bootstrap CI); `heteroes serve` / `heteroes worker` (self-hosted multi-machine, `--lab URL` pairing);
   `evaluation.promptFormat` raw/chat, `boxed-number@1` scorer with format reward, token/GPU-second accounting.
7. Remaining UI frictions in `frictions.md` (12, 15-review is done, 19 design question for the owner).
8. Rebuild **r11 candidate3** (`scripts/build-apps.sh`), packaged Linux checks, walk the journey again on it, write the
   flag-day checklist and ask the owner. Flag day itself is the owner's decision.
