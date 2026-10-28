# Session 4 checkpoint — continue here (2026-10-20, Codex)

Read `../AGENTS.md`, then this file. This is the latest handoff and supersedes stale operational state in older handoffs.
Branch **feat/v3-audit-recovery**. Starting commit **9a93237**. Latest implementation checkpoint **eafd5b5**; the following
handoff commit contains this document and cleanup receipts. Nothing pushed, tagged, merged, published or deployed.

The owner first asked to finish all system work, then explicitly requested a progress report and checkpoint because
usage was nearly exhausted. **This is a resumable checkpoint, not a completed-system/release claim.** The owner wants
Claude or Codex to review the whole implementation and continue without asking settled questions again.

## Owner decisions and authority (do not re-ask)

- The contribution is a correct, reproducible, measurable heterogeneous consumer-GPU ES system. No new ES algorithm and
  no GPU-days to prove learning. Prior GSM8K/Countdown learning/CSQA/parity work is parked until explicitly requested.
- Continue all unfinished system work autonomously, in order. No subagents. Meaningful tests before behavior, scratch
  mutation checks, logical commits, Vietnamese brief communication, English code/general docs. Never push/tag.
- SSH and GPU use on this 5070 Ti and both loaned 3060s is authorized for this continuation, including Windows test
  install/pair/run/uninstall. Endpoints: `thao_nguyen@100.92.20.58`, `quang@100.99.227.8`. Owner supplied SSH/sudo
  credentials in conversation; **they are deliberately absent from repository and handoff**. Existing SSH keys worked
  throughout this session. Try BatchMode first; no credential is needed for the already working key path.
- Thao's WSL was restarted by the owner and SSH worked again. Real native Windows coordination has now been demonstrated.
- Isolated lab/test Worker data may be deleted. Restoring Thao's original Worker is **not required**, overriding older
  session-2 instructions. Never launch/approve/enable its revoked public identity `3060-thao`.
- Live-lab experiment/account wipe is reserved for the **owner-selected r11 flag day**, not now. Lab and workers switch
  together: r10 rejects the new updateSecondsPerSeed payload. Push/tag/deploy/public installer publication remain owner-only.
- Any Linux/Windows/GPU/CPU machine may coordinate. CPU admission checks updates, not GPU text equivalence. Do not invent a
  full-model speed estimate from a tiny CPU vector. GPU workers still need their own model qualification.
- Python reward/coefficient code is fully open on the managed web lab (owner decision supersedes old declarative-only
  restriction). Frozen code runs on the coordinator in a bounded child process, never on GPU workers. It is not a sandbox;
  the existing SECURITY-NOTES describes the authority risk. Failures are not reward zero.
- Linux headless installation should be one `curl .../install-worker.sh | bash` line. The installer/resources already exist;
  the frontend download integration is still unfinished below.
- New-model qualification choices were Qwen3-0.6B and SmolLM2-360M-Instruct, completed in session 3.
- Frozen `es/update.py` reciprocal correction was separately approved and landed in **238dbd8** before this session.
  No further frozen numerical changes are authorized. Session 4 leaves noise/es/ledger/generation_record.py unchanged.
- Keep Conda ai and heteroes-match unchanged. No /mnt/sekai. Verify Archive UUID **10443D1F443D094C** before writing;
  runtimes/private control state stay on system disk. Use HETEROES_GPU_ACCEPTANCE=1 and explicit --gpu where supported.

## Completed before this session (baseline context for review)

See `handoff-session3-next.md` for the immediately preceding checkpoint. Relevant existing commits:

| Commit(s) | Work already present at 9a93237 |
| --- | --- |
| 699731e, c1a5d6d | Runtime provenance; recovery accepts Python-scored plans |
| 2965485 | Headless heteroes-worker and one-line installer/builder |
| 2d6d860 | Real new-model qualification on 5070 Ti app and Quang 3060 CLI |
| 57c88ab, 95245b4 | v3 hf_compact, 500 GSM8K-row text parity, modest 1.03–1.05x measured ratio |
| efe8e33 | Managed Python scoring/coefficient rules |
| 73f6b91, 8801f8e | File-backed datasets, default 1 GB / 10 million rows, admin limits |
| 238dbd8, ff226fd | Approved reciprocal update fix, any-GPU coordinator and update estimate |

Earlier researcher journey, sampler/default-coordinator/request-to-join, audit/recovery, SDK and r11 profile work are in
`handoff-system-finish.md`, `handoff-system-finish-next.md` and their evidence. The previous full check was before this
session, **not acceptance of the new code**. Review current source rather than treating old handoff TODOs as still open.

## Session 4 commits and evidence

| Commit | Result | Evidence under docs/evidence/ |
| --- | --- | --- |
| 66d3fe7 | CPU-only coordinator profile/admission/routing; known-answer update oracle; no fake GPU identity/reservation | 2026-10-20-cpu-coordinator (12/12 mutants killed) |
| 3b0ba25 | heteroes eval/compare: verified checkpoint replay, greedy/sampled outputs, unbiased Pass@K, majority tie rule, paired statistics | 2026-10-20-eval-compare (7/7) |
| 9dece34 | Standalone serve/worker plus serve --lab using installed CLI bridge and normal approval/ON; real Windows coordinator receipts | 2026-10-20-distributed-cli (7/7), -lab-cli (7/7), -windows-coordinator |
| 94e6257 | Isolated vLLM feasibility measurements and exact checked restore, no runtime integration | 2026-10-20-vllm-probe |
| 46c0834 | Raw/chat prompt option, boxed-number scorer, optional token/GPU-time sidecar through backend/web/recovery; file-data eval fix | 2026-10-20-research-options (7/7), -usage (9/9) |
| eafd5b5 | WIP Linux CLI build/preparation manifest and private URL rewriting; frontend still missing | 2026-10-20-linux-downloads |

Every evidence directory has a README with scope/limits and failed intermediate receipts. Do not rewrite existing
receipts or runtime/artifacts. Latest checkpoint receipts: `2026-10-20-session4-checkpoint/`.

### CPU coordinator and CLI behavior

- CPU profile `coordinator-cpu-v3` uses canonical noise plus two repeats of a fixed 200003-element FP16 update with three
  seeds and an independent NumPy oracle. Supports Linux/Windows CPU; excluded from worker/probe lists and GPU reservations.
- `heteroes-worker selftest --device cpu`; join with --coordinator/--host; config carries device:cpu into runner, whose child
  hides CUDA. CPU Worker execution is refused. Per-model text qualification is skipped only for the CPU coordinator.
- `heteroes eval` verifies model/schema, recorded update hashes and ordered row/scorer identity. Samples use explicit seed
  rules; compact remains greedy. Compare requires paired rows/scorer/split/count; reports B-A, fixed/broke, exact McNemar
  and seeded paired bootstrap. New file-backed evaluation validates the dataset against recipe.data before decoding.
  It materializes the selected split; no bounded-memory evaluation claim is made.
- Standalone workers fetch authenticated pinned recipe/plan/data, verify local model/schema and replay updates. Bootstrap
  is inline data; large file-backed transfer belongs to the managed route. Shared token is an environment variable,
  never argv. Python source stays coordinator-only. Windows LoRA requires a transferred pinned initial adapter.
- `serve --lab` uses an installed Linux CLI Worker, private user access token HETEROES_LAB_ACCESS_TOKEN, normal pairing,
  workspace approval and boot-scoped contribution ON. Never autoapproves/enables. Uploads model/dataset via signed routes,
  freezes Python source, submits the experiment, and writes nonsecret idempotent lab-offer.json. Managed paths support
  FP32/canonical CPU noise and reject unsupported standalone flags. CPU/API tests pass; real packaged acceptance remains.

### Real native Windows result

Native Windows Thao RTX3060 was coordinator; Quang WSL RTX3060 generated candidates. Full Qwen2.5-0.5B FP32, canonical CPU
noise, N=4, two generations, distinct-character Python reward. All records, 32 texts, eight rewards and both children match
an independent local 5070 Ti run. Children begin **5e1cc555** and **88733e3f**; both updates change >493M FP16 elements.
This is standalone staged-source acceptance, **not candidate3 installer/managed-lab or Windows CPU acceptance**. Audits
were off (one generating worker); no speedup or learning claim. Source digest inventory is committed with receipts.

### vLLM result and decision boundary

Separate disposable venv used vLLM0.32.0, Torch2.13+cu130, Transformers5.19; project remains Torch2.13+cu132/TF5.17.
On 64 synthetic prompts, base texts match HF0/64 differences; perturbed3/64 differ. All170 packed parameters were checked
against HF after reload, then exactly restored. Decode medians improve about1.27–1.30x, but checked reload/restore each take
about1.37s **including full tensor comparisons, RPC, file reads and sync**. Those are not raw-copy or ES-throughput times.
Pinned-project HF-only control has the same weights/texts as isolated HF. No vLLM engine was integrated or chosen as default.
The original plan's longer500-row GSM8K, batch/order invariance and3060 matrix was **not executed**; this is only the
small feasibility probe. Ask owner only if proposing actual APPROXIMATE engine integration; do not silently widen claims.
The disposable7.9GB venv was deleted after receipts were frozen; system disk now has about15GB free. Environments unchanged.

### Prompt/scorer/accounting details and review hotspots

- Optional promptFormat absent=chat preserves prior recipe hashes. Explicit raw bypasses template and rejects systemPrompt.
- boxed-number@1 uses the LAST plain decimal box, exact Decimal equality, grouping commas, optional formatReward0<=r<1.
  Malformed final/nested/fraction boxes score0. Large integers have a regression test (no floating-point comparison).
- Usage metadata never enters numerical identity. Workers count token IDs through first EOS inclusive, exclude later pad;
  old evaluation serialization stays unchanged unless opt-in. Negotiated usageReporting keeps new workers compatible
  with older coordinators; old workers produce partial coverage.
- usage.sqlite is a separate private SQLite sidecar, not frozen ledger schema. Candidate/audit receipt identity includes
  candidate, attempt, worker and kind. Duplicate receipts do not add usage; changed retry metadata is refused.
  Canonical completion commits happen before optional sidecar write; accounting errors cannot invalidate canonical reward.
- GPU seconds are synchronized successful worker wall time (audits included) plus coordinator GPU updates. CPU0, idle,
  validation and unreported failures excluded. Not energy/utilization billing or independently attested worker measurement.
- Snapshots/backend/web expose per-candidate/per-generation/total usage. Changed worker event glob now excludes config JSON.
- Recovery now includes SQLite backup and hashed JSONL split files; v2 max12 covers LoRA+selection+3splits+usage. V1 unchanged.
- Review especially usage partial-count semantics across retries/audits/resume, error isolation, EOS handling, snapshot
  projections/recovery trust boundaries, CPU reservations, lab-offer idempotence/source privacy and statistical assumptions.
- New file-data evaluation and new download publisher behavior **do not yet have dedicated mutation coverage**.
  Existing16 research/usage mutants pass, but do not imply coverage for the later additions.

## Latest verification (not the full release gate)

- Final focused runtime suite after formatting: **59 passed**, `2026-10-20-usage/checkpoint-final.log`.
- Earlier broad usage/product/audit/worker/recovery regression: **81 passed**, usage/regressions.log.
- Final backend/options/usage/installer/web suite: **10 passed**, linux-downloads/checkpoint-final.log (one dependency warning).
- Frontend TypeScript, three review-unit tests, i18n, repository Ruff lint/format and Prettier all pass. Receipts are in
  research-options/, usage/ and session4-checkpoint/. Ruff checked388 files.
- Frozen numerical diff against9a93237 is empty; checkpoint/state.json records it. Source package and browser/Electron/full
  runtime/backend checks have **NOT** been rerun across the final combined code. Do not claim ALL PASS/check-all or r11 ready.

## Current machines, private state and cleanup

All three isolated devices were confirmed contribution OFF, allocatedTo null before shutdown. Verified isolated driver
PIDs received SIGTERM through their graceful handlers: local Worker3388117 and Server3386307. Their apps, bridge and backend
exited; port8790 is closed. Quang's CLI agent2679 stopped. Native Windows standalone coordinator16304 and Quang standalone
worker5099 had already completed/exited. Local standalone-test shared token and the matching /tmp token on both remote WSLs
were removed. Final cleanup receipts are in session4-checkpoint/. No active test/GPU job is intentionally left running.

The public lab was untouched; local-lab.py status still showed all3 services alive. Never operate it via these isolated
scripts or manually kill its processes. The local isolated keyring/Xvfb helper processes may outlive their drivers; if
cleaning them, verify exact ownership/cwd first. Do not kill a public process or use pkill -f.

Preserved paths (private files may contain credentials/leases; do NOT print/commit their contents):

- Isolated lab `.scratch/isolated-lab/`, sysfinish-q1 packaged app, workspace **bcbece5a24834ac28e358fc49db1343f**.
  Restart using start-q1.sh there with a fresh redirected log, then worker5070/start-q1.sh. Upgrade to a new package only
  while drained. API helper api.py must run with cwd there; login('researcher') owns its devices (admin requests can404).
  Never print login returns. Worker driver reads commands.jsonl; contribution action takes args.enabled; SIGTERM closes app.
- Local model `/mnt/Archive-2tb/heteroes-local/models/7ae557604adf67be50417f59c2c2f167def9a775`.
- Thao SSH lands in Ubuntu WSL. Native PS is `/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe`.
  Helper `.scratch/windows-system-finish/run-ps.py FILE` invokes encoded PS. Native Windows Tailscale **100.81.45.107**.
  Model `D:\HeteroES-Worker-data\models\7ae557604adf67be50417f59c2c2f167def9a775`; runtime
  `D:\HeteroES-Worker-data\runtimes\14a541f25093\python\python.exe`. Staged source `D:\HeteroES-session4-20261020\src`.
  C: last had~28GB and D:~893GB free; recheck. `.scratch/windows-system-finish/action.py` and driver.cjs support the
  installed TEST Worker actions. Private result files can contain tokens: only export selected nonsecret fields.
- Quang CLI home `~/.local/share/heteroes-worker`, runtime8216195de161/python/bin/python. Agent can restart via installed
  heteroes-worker run. Standalone source `/tmp/heteroes-session4-20261020/source/src`; output
  `~/.local/share/heteroes-session4-20261020/worker`. Quang has no rg; use a small Python script or grep remotely.
- Native Windows parity raw ledgers/events under `.scratch/session4-windows/`; ledgers contain leases, never commit them.
  Its baseline published weight artifacts (~3GB) alone moved with SHA checks to Archive and scratch published is a symlink:
  `/mnt/Archive-2tb/heteroes-local/evidence/2026-10-20-session4-baseline-published`. Private ledger stayed system-side.
- vLLM generated weight artifacts are under Archive evidence/2026-10-20-vllm-probe-weights2, -weights3, -weights4,
  -pinned-hf (inspect paths before cleanup). Final harness and package freeze are committed; private probe scripts/logs
  remain .scratch/vllm-probe. Only its disposable venv was deleted. No other runtime/environment was moved.

## Unfinished — recommended resume order

1. Review commits9a93237..eafd5b5 and receipts, focusing on the hotspots above. Finish the **WIP Linux download page**:
   useInstallerManifest needs a linuxWorker shape; create a reusable Linux CLI section with a copyable one-line command
   using the server-provided installer URL. Mount in InstallerDownloads, GetStartedPage and LabDevices; add translations
   and meaningful browser checks. Existing UI currently ignores linuxWorker. Avoid exposing implementation details to users.
   Review publisher preflight order, old app-only compatibility, tamper checks, and atomic replacement of a previous stable
   script alias. Add mutation checks for new publisher/route behavior and file-backed eval identity rejection.
2. Run full `scripts/check-all.sh docs/evidence/<fresh-date-name>/checks` **alone**, no concurrent builds/source edits.
   Fix real failures, preserve each receipt. Proper runtime test cwd is runtime (some subprocess helpers use relative scripts).
3. Rebuild final **r11 candidate3** from final code on verified Archive, fresh BUILD via scripts/build-apps.sh. It refreshes
   runtime/profile/defaults resources: commit them after reviewing source digests; never format pinned resource profiles.
   It now also builds OUT/cli. Use publish-local-installers.py **--prepare-only** for reviewable hashed installers, never
   publish them. Run `scripts/build-apps.sh --check .scratch/<fresh-check>` and actual Linux Server/Worker packaged checks.
4. Upgrade/restart ONLY isolated lab/workers. Real managed `serve --lab` CPU coordinator + GPU worker acceptance remains;
   show short deterministic parity and usage, no learning run. Browser-walk final researcher flow/options/accounting.
   CPU fixture tests and the standalone native Windows result do not replace this check.
5. If Thao is available, test final candidate3 Windows install/runtime/coordinator and normal stop/restart/uninstall.
   Use test profile/data, pinned LoRA adapter if needed. No public revoked identity. Latest owner decision removes old
   original-Worker restoration requirement. No new authorization question is needed for these already authorized tests.
6. Drain/off/stop test devices, preserve exact evidence, update a final self-contained review handoff (the owner's explicit
   request) with commits, tests, artifact locations, remaining limits and live state. Leave clean, no push/tag/deploy.

The vLLM long benchmark matrix is a documented probe limitation, not an integrated decoder TODO. Do not start a learning
run or silently spend GPU-days. Do not change frozen numerical files to work around a new test without owner approval.

## Owner-only r11 flag-day checklist (prepare/review; do not execute)

- Complete final gates and review prepared hashes, build/source/profile identities, platform checks and known limitations.
- Owner picks switch window and explicitly authorizes deployment and live account/experiment wipe. Until then preserve data.
- Drain workers/coordinators and confirm no allocations. Back up current deployment and required private recovery/operational
  state; keep secrets private. Define rollback before destructive changes; wiped live data requires retained backup to undo.
- Upgrade lab and all workers together for v3/r11 and updateSecondsPerSeed compatibility. Retire old active execution paths
  only as planned while retaining old numerical replay validation. Do not claim mixed r10/r11 compatibility.
- Execute only the owner-approved live wipe, publish exactly reviewed installer/CLI bytes, verify private/public transfer
  URLs, device/account approval, self-tests and a short managed parity/audit run. The revoked identity stays revoked.
- Record deployment/build hashes, smoke/rollback outcomes and new live state. Push/tag remain separate explicit owner actions.

Resume prompt:

> Read AGENTS.md and docs/handoff-session4-next.md, review the checkpoint, then continue Unfinished in order. Preserve the
> owner's settled decisions; finish with a self-contained handoff for Claude/Codex review. Do not push, tag or deploy.
