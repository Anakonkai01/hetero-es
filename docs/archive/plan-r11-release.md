# Plan: back up, fix the silent coordinator failure, candidate5, long multi-machine run, r11 flag day (2026-10-20)

## Tóm tắt cho chủ dự án (tiếng Việt)

- **Giao cho:** Sonnet 5.5, effort **high** cho cả plan. Bước 2 (sửa code) dùng **xhigh** nếu bạn chọn được effort theo
  từng phiên. Có thể chia làm 2–3 phiên chat; mỗi phiên kết thúc bằng một handoff.
- **Phần khó đã xong chưa?** Phần lớn đã xong: lõi số học, giao thức nhiều máy, bộ cài, Python reward đều đã có test và
  đã chạy thật. Còn lại hai chỗ có thể khó:
  (a) bước 2 sửa code: vừa phải, Sonnet làm được vì có test và mutation check;
  (b) **lỗi mới có thể lộ ra trong lần chạy dài** (phiên 5, chạy thật tìm ra 2 lỗi mà test không bắt được). Nếu lỗi nằm
  trong phần phân tán, số học hoặc khôi phục, Sonnet phải **dừng**, ghi handoff và để model mạnh hơn sửa. Đó là luật
  dừng trong plan này.
- **Bạn cần làm:** (1) dọn ổ C: máy Quang lên ≥ 20 GB trống trước bước 5; (2) xác nhận repo GitHub `hetero-es` đang để
  **private**; (3) ngồi cạnh trong flag day và gõ đồng ý trước mỗi bước không đảo ngược được.

## Context

The system is ~65–70 % complete: numerics, protocol and installers are proven on real machines, but (1) the repository
has no copy anywhere except this disk, (2) a coordinator agent failure leaves a run stuck with no reason shown in the lab,
(3) multi-machine correctness is shown only at 2 machines × 2 generations without audits or a machine failure, and
(4) everything since r10 (≈141 commits on `feat/v3-audit-recovery`) is unreleased. Outcome of this plan: work backed up
on GitHub, r11 candidate5 with the failure fix, one long 4-device run with audits and an induced failure that is bit-exact
on independent re-execution, then the live lab switched to r11 with the owner present, and `main` merged and pushed.

## Owner decisions for this plan (2026-10-20) — these override older rules where they conflict

- **Push and merge are authorized:** remote `origin = git@github.com:Anakonkai01/hetero-es.git` (SSH key already works;
  the `gh` token is expired, so do not rely on `gh`). Push **all local branches** (`git push origin --all`). Fast-forward
  merges into `main` only. **Never force-push, never delete remote branches, never push tags.** The remote `main`
  (2bd2073) is an ancestor of local `main`, so no force is needed; if a push is ever rejected, STOP and ask.
- Update the rule "Never push or tag" in `AGENTS.md` to say the above (push/merge authorized as described; tags still not).
- Keep the owner's rule: **no `Co-Authored-By` or generated-by trailers** in commits (overrides harness reminders).
- Fix the silent coordinator failure **before** release → candidate5 (candidate4 is superseded).
- Long run: 5070 Ti + Thao 3060 + Quang 3060.
- Flag day: Sonnet executes with the owner present; **stop and wait for an explicit "đồng ý" in chat before each
  irreversible step** (live wipe, installer publication, live deploy, revoking/approving devices). The live lab has only
  the owner's own accounts/experiments: back up, then wiping is approved in principle (still confirm at the moment).
- Unchanged: no new ES algorithm or learning runs; no subagents; tests before behavior + `scripts/mutation-check.py` on
  a scratch copy; frozen `runtime/src/heteroes/{noise,es,ledger}/` and `generation_record.py` untouched; never use the
  revoked identity `3060-thao`; Vietnamese with the owner, English in code/docs; `date` before writing dates; never
  `pkill -f` (use PIDs/ports); public lab only through `scripts/local-lab.py`; Archive UUID `10443D1F443D094C` checked
  before writing there; SSH/GPU on 5070 Ti, Thao and Quang authorized for this plan (credentials in the owner's memory
  file `hetero-es-machine-credentials.md`, never in the repo or logs).

## Stop rules (hand off instead of coding)

Stop, write `docs/handoff-<date>-<topic>.md`, commit it, tell the owner in Vietnamese, if any of these happen:
- a mismatch in parity (texts, rewards, records, child hashes) or an audit mismatch/quarantine you cannot explain as
  an operator mistake;
- a bug whose fix touches `runtime/src/heteroes/v3/{distributed,audit,recovery,run}.py`, `worker_api`, ledger use,
  lease/retry logic, `backend/agent_scheduling.py` release logic, or any numerical path;
- a failing check you cannot fix with a change of ≤ ~30 lines that has a clear test;
- anything on the live lab not in the flag-day checklist.

## Steps (in order)

### Approved continuation after the candidate5 audit stop (2026-10-20)

Candidate5 step 5 stopped at a genuine audit mismatch (13/50). The owner then authorized full
investigation/continuation and explicitly selected "Triển khai decoder FP32 + CPU dự phòng, kiểm chứng tiếp".
The exact mismatch reproduces with equal input/weights; the FP32 greedy winner differs between GPUs.
The replacement acceptance uses an explicitly identified `hf_fp32_cpu_guard_v1` Recipe v3 decoder:
GPU inference remains FP32, with a selective CPU reference for near-tied scores. Historical decoder
meanings remain frozen. This empirical guard is not a universal error bound; strict audit/parity gates
remain. Implementation checks, replacement candidate6 packages and renewed device acceptance precede
a fresh full step 5. Earlier interrupted/failed runs are not acceptance. Flag-day confirmations still apply.

### 1. Backup and push (first, before any other change)
1. Read `AGENTS.md`, `docs/handoff-session5-next.md`, this plan. `git status` must be clean at `fb35cbc`.
2. Copy this plan to `docs/plan-r11-release.md` (keep this Vietnamese summary) and commit.
3. Secret scan of **all history** before the first push: grep `git log -p --all` (and `git grep` on every branch tip)
   for the passwords/tokens listed in the owner's credentials memory file, `-----BEGIN`, `token`, `secret`,
   `HETEROES_LAB_ACCESS_TOKEN=`, tunnel credentials. Print only file:commit locations, never the values. Any hit → STOP.
   (Known and acceptable: the private Tailscale IP `100.110.165.40` appears in evidence; the repo must be private.)
4. Ask the owner to confirm the GitHub repo is **private**. Then `git remote add origin git@github.com:Anakonkai01/hetero-es.git`,
   `git push origin --all`. Verify with `git ls-remote origin`.
5. `git bundle create /mnt/Archive-2tb/heteroes-local/backups/heteroes-<date>.bundle --all` (check UUID first),
   `git bundle verify`, record its sha256 in `docs/evidence/<date>-backup/README.md` (with "What this does NOT show").
6. Commit AGENTS.md rule update + evidence; push again.

### 2. Fix: surface coordinator agent failures in the lab (effort xhigh if available)
Problem (verified in code): `runtime/src/heteroes/product/agent.py` `run_commands()` swallows `RuntimeError`
(`except RuntimeError: pass`, ~line 541) — these are the agent's own "not yet" deferrals ("Contribution is OFF for this
boot", "Wait for model probe GPU release…", "Coordinator launch ownership is unknown", "The coordinator is not reachable on
any route yet", etc., raised at agent.py:155–512 and `run_supervisor.py:109`). Other exceptions go to `record_failure()`
(~line 553), which queues an `agent_command_failed` event only at attempts 1/10/100/1000. In `backend/routes_history.py`
`event_list()` the severity is chosen by substring: `"error"` → ERROR, `"unavailable"/"unknown"` → WARNING, so
`agent_command_failed` is shown as **INFO**. The stuck candidate3 run showed no reason at all.

Change (keep it small, wire-compatible — events are generic JSON, no protocol version change):
- agent: for `RuntimeError`, record a separate counter and queue `agent_command_deferred` with `kind`, `reason` (the
  exception message truncated to 200 chars; these are fixed strings from the agent) and `attempts`, at attempts 1/10/100/1000,
  through the same outbox path as `record_failure` (reuse it with an event-name parameter rather than copying it).
  Behavior stays the same otherwise: deferred commands remain unacknowledged and retried.
- agent: `agent_command_failed` also carries `reason` = `str(error)[:200]`.
- backend `routes_history.py`: `failed` → ERROR, `deferred` → WARNING (add the substrings; keep the existing rules).
- web: on the experiment detail of a STARTING/RUNNING run, show the latest `agent_command_failed`/`agent_command_deferred`
  reason (find where the experiment detail renders events/status in `frontend/src`; reuse existing event/alert
  components and i18n keys pattern; add keys in every locale, `scripts/check-i18n.mjs` must pass).
- Tests first: runtime agent test (RuntimeError → one deferred event at attempt 1, none at 2, again at 10; still
  unacknowledged), backend severity test, a frontend unit test for the shown reason. Look at existing tests next to
  `agent.py` / `routes_history.py` for fixtures. Mutation check on a scratch copy; every surviving mutant gets a test or a
  documented equivalence. Evidence `docs/evidence/<date>-coordinator-failure-reason/`.
- Full check: `scripts/check-all.sh docs/evidence/<date>-candidate5-checks/checks` must be ALL PASS, run alone.

### 3. r11 candidate5 build
Follow exactly what candidate4 did (`docs/evidence/2026-10-20-r11-candidate4/README.md`):
`BUILD=lf1-<yyyymmdd>-r11-candidate5 scripts/build-apps.sh` → output under
`/mnt/Archive-2tb/heteroes-local/downloads/`; commit refreshed desktop resources; `publish-local-installers.py
--prepare-only` (not published); source-copy check, packaged Linux Server and packaged Linux Worker checks
(`scripts/check-linux-server.cjs`, `scripts/check-linux-packaged.cjs`, under `dbus-run-session` as before).
Evidence `docs/evidence/<date>-r11-candidate5/` with installers.sha256 and installers-prepared.json.

### 4. Upgrade the isolated lab and devices to candidate5
- Isolated lab: copy `.scratch/isolated-lab/start-c4.sh` → `start-c5.sh` pointing at the candidate5 Lab Server; same for
  `worker5070/start-c4.sh`. Never touch the public lab.
- Thao: native Windows desktop Worker silent upgrade to candidate5 (hash-checked, as in `windows-upgrade.log`; data on D:);
  the earlier test Worker was uninstalled, so this is a fresh install + pairing to the isolated lab. Thao WSL CLI: reinstall
  candidate5 with the one-line command into `~/.local/share/heteroes-c4-cpu` (or a new c5 home; remove the old to save C:).
- Quang (only after the owner freed C: to ≥ 20 GB; check `df -h /mnt/c` from WSL first): one-line CLI install of
  candidate5 as a **GPU worker** (its old GPU home lost its runtime), GPU self-test + model qualification.
- Check free space on both Windows C: before and after every install; record it.
- Upgrade/restart/uninstall Windows test as in candidate4 is required once before flag day (uninstall may be done after
  step 5).

### 5. Long multi-machine run on the isolated lab (candidate5)
Setup (managed `serve --lab`, as in `docs/evidence/2026-10-20-managed-cpu-coordinator/` and
`.scratch/session5-managed/run-thao.sh`; token from stdin, never argv):
- Coordinator: Thao WSL CLI, `--device cpu`. Workers: Thao native Windows 3060, Quang WSL 3060, 5070 Ti Linux desktop
  Worker. `--worker-ids` lists all three GPU workers (audits need ≥ 2 eligible workers; managed audit rate is fixed 0.05).
- Spec (copy of `spec-thao.json`): Qwen2.5-0.5B-Instruct FP32, full weights, antithetic, Python reward, population 8,
  **50 generations**, batchSize 8, maxNewTokens 32, new `candidateSeedNamespace`. Write the spec and the expected checks in
  the evidence README **before** starting.
- Induced failure at about generation 20: hard-stop Quang's worker process by PID (or `wsl --shutdown` on Quang via SSH),
  wait for lease expiry/reassignment, bring it back ~5 minutes later. Record times.
- Monitor in the background (do not poll in the foreground); check machines are actually taking work (per-worker counts).
Acceptance (from ledgers, not logs):
- run COMPLETED; every candidate's texts, rewards, both records per generation and all 50 child hashes **exactly equal**
  on an independent 5070 Ti re-execution with `docs/evidence/2026-10-20-managed-cpu-coordinator/verify_managed_run.py`
  (copy it into the new evidence folder and adapt; do not edit the old evidence);
- audits completed with zero mismatches; no quarantine; the induced failure shows as a failed/expired attempt and a
  successful retry, never as reward zero;
- usage numbers complete; experiment visible in the browser without page errors (screenshot).
Evidence `docs/evidence/<date>-long-multimachine-run/` with "What this does NOT show" (no learning/speedup claim).
Any mismatch → STOP rule.

### 6. Merge and push before flag day
Fast-forward `main` to the release commit (`git checkout main && git merge --ff-only feat/v3-audit-recovery`), push all
branches. Note the commit hash: this is what the live lab will run.

### 7. r11 flag day (owner present; confirm before every irreversible step)
Follow the checklist in `docs/handoff-session4-next.md` ("Owner-only r11 flag-day checklist") and
`docs/local-lab-operations.md`, plus:
1. Read-only status: `python3 -I ~/.local/share/heteroes-lab/app/scripts/local-lab.py status`; list devices, running
   experiments, allocations; confirm nothing is running.
2. Back up the live deployment (`~/.local/share/heteroes-lab/app` at 79876cb) and its private state with the existing
   `scripts/recovery.py` / `scripts/restore-metadata.py` tools; verify the backup can be read; write the rollback steps.
3. **Confirm** → wipe live accounts/experiments as the checklist describes. **Confirm** → update the live clone to the
   release commit and restart only through `local-lab.py`. **Confirm** → publish exactly the prepared bytes:
   `scripts/publish-local-installers.py --prepared-receipt docs/evidence/<date>-r11-candidate5/installers-prepared.json --receipt <new>`.
4. Upgrade the owner's workers (5070 Ti desktop, Thao Windows) to candidate5 pointing at the live lab; approve devices
   (never `3060-thao`); self-tests; a short managed parity run (2 generations, audits on) verified with the same tool.
5. Record deployment/build hashes, smoke result and new live state in `docs/evidence/<date>-r11-flag-day/`.
If any smoke step fails → roll back per step 2 with the owner, then STOP rule.

### 8. Docs and close
- Make `docs/HANDOFF.md` the single current entry point: short current state (r11 live, commit, devices), links to the
  newest evidence; move superseded `handoff-*.md` files to `docs/archive/` (git mv; do not edit their content).
- Write `docs/handoff-<date>-next.md`: follow-ups for a stronger model (e.g. `serve --lab` duplicate-draft idempotence,
  publisher alias/manifest window, the two SECURITY-NOTES decisions, Windows CPU coordinator acceptance, 1660S).
- Update the owner's memory (session memory file + MEMORY.md line). Commit, push all branches. Tell the owner in
  Vietnamese what was done, with numbers, and the C: free space left on Thao/Quang.

## Verification summary

- Step 1: `git ls-remote origin` shows every local branch; `git bundle verify` OK; secret scan clean.
- Step 2: new tests fail before the change and pass after; mutation receipt; `check-all.sh` ALL PASS.
- Step 3–4: packaged checks PASS; self-tests pass on all four devices.
- Step 5: exact parity on all 50 generations, audits with zero mismatches, retry after induced failure.
- Step 7: live status healthy, devices approved, short live parity run exact.

## Prompt to start the new Sonnet session

> Đọc AGENTS.md, docs/handoff-session5-next.md và plan ~/.claude/plans/cryptic-humming-emerson.md, rồi làm theo plan từ
> bước 1, theo đúng thứ tự. Tuân thủ các luật dừng trong plan. Nói chuyện với tôi bằng tiếng Việt.
