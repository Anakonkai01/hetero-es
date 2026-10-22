# Candidate14: session handoff to Claude (2026-10-22, ~23:30 Vietnam)

The owner requested closing this session at 15% remaining usage and handing
unfinished work to Claude. **Implementation and real run are done; final product
acceptance, cleanup, push and FF main remain.** Do not restart from the prototype
or re-grill settled choices. Read `AGENTS.md`, this file, and the evidence README.

## Scope and decisions already authorized

Both systems and UI/UX, including the whole external
`/home/pc5070ti/projects/need-fix.docx` and finding-13 handoff. CPU V2 first;
CUDA enablement/chunk 128 deferred. Historical V1 is immutable, saved engine is
resumed. New runs default to V2. Generated Python thresholds/pinned digest, V2
max eight noise threads (V1 sixteen), environment override retained. Correctness
has priority over equal V1 speed.

`needs_private_route`: persist a per-run block, explain it, let other workers
continue; Retry makes exactly one attempt, a new run re-evaluates. This is the
owner's **temporary workaround**, not public weight recovery. Identity snapshots
are first-participation metadata outside configHash. Live/replay exclusive,
speed exits Live at current playhead, Live jumps latest. Admin cannot remove
their own access; profile security remains available. Real OS telemetry only,
missing reason, compact six metrics with sensors/power in details. Preserve
brand/dark/light/languages; dataset/artifact pagination ten, no merge/delete.

Remote work, GPU acceptance, lab deployment, publishing/installing candidates,
cleanup of the exact temporary nhut rule/folder, feature push and FF main were
explicitly authorized. No need to ask again. GPU commands need `--gpu` where
supported and `HETEROES_GPU_ACCEPTANCE=1`; CPU commands use
`CUDA_VISIBLE_DEVICES=''`. Credentials are in private session/vault files;
never print/commit them. Do not write a password into this handoff. Do not touch
Conda `ai` or `/mnt/sekai`. Verify Archive UUID before writes.

## Current source and deployment

Repo `/home/pc5070ti/projects/heteroes`, branch `feat/real-user-c13`, not pushed.
Logical implementation commits:

- `4c0e166`: V2, qualification/admission, persistent worker block/retry,
  identities, admin guards, telemetry, tests and ADR-011.
- `083fbfa`: DOCX web/shared resource UI and Live/replay redesign.
- `f51915a`: candidate14b, reference V2 + SDK captured before Server archive.
- `299dcbe`: SDK qualification caches/requests use the requested engine.
- `f70b05f`: candidate14c packaged SDK fix; **live lab is deployed here**.
- `937c48a`: local paired Worker ON without an account session.
- `95922c2`: candidate14d packaged paired-device controls; **published installers**.
- `c8d563a`: final regression: policy denials never fall back to account credentials.

Linux CLI agents are C; native Windows Desktop installed D. Same runtime archive
SHA `630ff292d0c6bb18a4ce87505d62a485ef42a44cae1aa4cb973f01588d4cea2c`.
Do not confuse Desktop profile hash `f731d5a12cb4` with CLI archive hash prefix.
Lab backups are private under `~/.local/share/heteroes-lab/backups/`:
`candidate14-20261022`, `candidate14c-20261022`. Deploy receipts/scripts in fresh
`docs/evidence/2026-10-22-candidate14/`; only `local-lab.py` changes lab state.

Pre-existing untracked files belong to the previous session; preserve:
`docs/evidence/2026-10-22-candidate13/deploy-lab-c13c.log`, `monitor.pid`.
Existing evidence and runtime artifacts stay immutable. New evidence is ~29 MB;
preserve intermediate failures. Never claim a failing combined log passed.

## Verification already done

Full combined `checks-final-progress.log` ALL PASS: runtime 2664/102 skipped,
backend 437, remaining lint/format/i18n/import/unit/type/browser/Electron checks.
Later `checks-release/` passes all except worker-unit, which raced newly added
red tests during the native fix; final current Worker unit rerun is **92 pass**
(`worker-unit-final.log`). Targeted later SDK/device/types/build/i18n checks pass.
Final scratch mutation checks kill 6 runtime + 6 backend + 2 SDK + 2 device ON
mutants. V1 golden fingerprints unchanged, table regeneration byte-identical.

Source GPU full/LoRA positive/negative, exact restore, perturb and update hashes
match on nhan glibc 2.43, nhut 2.39 and native Windows. Installed CPU boundaries,
fingerprints, known-answer updates and portable source SHA also match all three
(`source-gpu-parity.json`, `installed-parity.json`). Native D GPU self-test passes.
Whole-model timings are exploratory single samples, V2 updates slower than V1;
do not claim a speedup. Fixtures cover UI keyboard, account guards, pagination,
375/768/1440 overflow and Electron station. Real final UI review remains.

## Real acceptance run completed

Run **`2dd6e2f78aa84e60aa5bafaed3fe2c6b`**, notebook SDK submission, nhan
coordinator; workers nhan + nhut + native Windows Thao. Full Qwen 0.5B, FP32,
10 generations, 8 antithetic candidates, batch 4, sigma/alpha .001, last-integer.
Declared in `acceptance-plan.md` before queueing. Nhut's public-only rule stayed
active. **10 updates, 80 completions, 3 selected/completed audits, zero mismatch,
no worker blocks.** Contributions: nhan 47, nhut 22, Windows 11. All reservations
released (`live-after-run-workers.json`). This is system acceptance, not learning.

Independent replay copies contain only numerical documents/ledger/dataset,
under `.scratch/candidate14/managed-replay` and nhut `~/candidate14-managed-replay`.
First replay attempt omitted format-3 split JSONL files and failed before model
execution; retained logs. Split files were added; second attempts use installed
runtime and explicit V2 engine in `verify_managed_run.py`. Both second attempts exit zero: **ALL EQUAL, 10/10 child hashes**.
`managed-replay-summary.json` records nonzero/changed generations and final hash.
`managed-replay-*-second.*` are the successful receipts. No candidate text regeneration is
claimed by `--regenerate none`; the three real audits are independent text checks.

## First remaining task: native Windows approval display

Real D runs signed out and service-level ON works. However local settings still
carry `device.approvalStatus=PENDING` while server is APPROVED. `Service.status`
refreshes `/api/v1/devices` only when `userToken` exists, and `stationView`
blocks OFF-to-ON based on that stale value. **Native user journey is not accepted.**
Do not resolve by disabling approval checks, approving again, changing account
credentials, or merely editing cached settings.

Write regressions first. Likely use the authenticated device poll's existing
approval result, expose it through bridge state and refresh the Desktop's
public device projection without an account token. Preserve actual PENDING /
REVOKED/403 behavior and server authorization. Mutation-check, rebuild the next
immutable candidate, install native Windows, test OFF/ON while signed out,
pending/revoked guards in fixtures, and optional collapsed account sign-in UI.
Rerun only checks affected by new changes; full stable check if justified.

## Machines, paths and safe continuation

Fresh reads confirmed APPROVED/ONLINE/ON, idle after the run (old AGENTS revoked
note refers to a different historical identity; do not change any approvals):

| Machine | Worker | Device |
| --- | --- | --- |
| 5070ti-nhan | cli-71b757062fd9 | dbe5254b78de4c038550b8b90df13899 |
| 5070ti-nhut | cli-34312a79fbbc | 093cd4deafe84eb3adb704f76cfed64d |
| 3060-thao | desktop-d9017660e75f | 922b858a244f451eb3a154b612d20a4c |

Quang/1660S offline; do not wake or change them. Nhut SSH:
`heheboiz@100.108.195.50`. Windows through WSL:
`thao_nguyen@100.92.20.58`; invoke native
`/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe`.

Lab `https://lab.heteroes.site`; compute `https://compute.heteroes.site`;
live backend `http://100.110.165.40:8002` (same session accepted, useful for
read-only snapshots when edge stalls). **Port 8790 is an older isolated lab, not
the public lab.** Instance `34d68e114a5316bb76de9c12f657dff0`.
Session `~/.config/heteroes-demo/session.json` expires around 06:00 23 October.
Do not print it. SDK `Lab.from_session()`; `.scratch/candidate14/sdk-final` is
the extracted published C SDK with all 118 Python sources checked against source.

Local installed CLI Python/source:
`~/.local/share/heteroes-worker/runtimes/630ff292d0c6/{python/bin/python3,src}`.
Model `~/.local/share/heteroes-worker/models/7ae557604adf67be50417f59c2c2f167def9a775`.
Coordinator root `~/.local/share/heteroes-worker/agent-state/runs/<run-id>`.
Do not print/copy config/assignment/device-grants files; they contain credentials.
SQLite backup API for a live ledger; raw ledgers stay private and uncommitted.

Windows app `C:\Users\Thao Nguyen\AppData\Local\Programs\@heteroesworker\HeteroES Worker.exe`;
user data `C:\Users\Thao Nguyen\AppData\Roaming\@heteroes\worker`;
runtime `F:\HeteroES-Worker-data\runtimes\f731d5a12cb4`, model under `F:\HeteroES-Worker-data\models`.
Runtime completion marker is **READY.json**. Do not use old C9 `29c6db0c83bb`.

Current GUI was launched with localhost renderer debug 19323, main inspect
19324. No account credentials were entered. `.scratch/candidate14/native-driver.cjs`
is copied at `F:\HeteroES-Worker-data\candidate14-control\driver.cjs`.
Actions `status`, `selftest --gpu`, `contribution <args-json>`, `quit` use the
actual packaged IPC. Results are private; sanitize before committing.
`run-windows-ps.py` ensures UTF-8. Use DotNET ProcessStartInfo / WaitForExit for
the driver; direct PS invocation of this GUI executable misreports LASTEXITCODE,
and Start-Process -Wait waits the detached GUI tree. Existing
`windows-runtime-d.ps1` launches/selftests/enables/reads status successfully but
its outer SSH may remain waiting for the GUI lifetime. Do not kill Worker/agents
to close that helper. Quit safely by RPC, wait for actual app processes to exit,
then install/relaunch. Keep data/pairing and contribution choice.

Before close-out, relaunch normally **without debug ports**, verify actual ON
and healthy agent, and remove only own temporary probe/control/installer files.
Do not remove real runtimes/models/artifacts or other people's data.

## Close-out checklist

1. Confirm independent 10/10 child hash replay on both Linux hosts. If needed,
   use the numerical verifier with installed source, `--device cuda --gpu
   --regenerate none` and GPU environment guard. At least one update must be
   nonzero; use records/hashes, not learning claims.
2. Fix/accept the signed-out native approval refresh above. Record final
   actual-OS telemetry and live/replay screenshots, including narrow layout.
3. After acceptance remove the **exact** nhut temporary rule:
   `sudo iptables -D OUTPUT -d 100.64.0.0/10 -m owner --uid-owner 1000 -m conntrack --ctstate NEW -j REJECT`.
   Record its absence. Delete `~/f13-diag` and own `~/candidate14-source-probe*`,
   `~/candidate14-managed-replay*` after receipts. Windows own temps are
   `candidate14-source-probe*`, `candidate14-control`, `candidate14*-setup.exe`
   under the data drive. Preserve logs/receipts first.
4. Review final evidence limits, update this handoff/README. Commit logical
   groups. Feature push then FF main are authorized **after acceptance**;
   never force/delete/tags/trailers; stop and ask if push rejected.
