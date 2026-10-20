# Session 3 handoff (2026-10-20 evening, Opus)

Read `../AGENTS.md`, then this file. Branch `feat/v3-audit-recovery`, nothing pushed. Owner answers for this session are
in AI memory (`hetero-es-session3-decisions-2026-10-20`). Each commit below has its evidence folder with
**What this does NOT show**.

## Done (commits)
- `699731e` provenance fix; `c1a5d6d` recovery accepts Python-scored plans.
- `2965485` headless Linux Worker CLI `heteroes-worker` + `scripts/build-linux-worker.py` + `scripts/install-worker.sh.in`.
- `2d6d860` Qwen3-0.6B + SmolLM2-360M qualified on the 5070 Ti app and the 3060 Quang CLI (WSL).
- `57c88ab`, `95245b4` hf_compact for Recipe v3 (equal texts on 500 GSM8K rows, 5070 Ti and 3060; only 1.03-1.05x at chunk 16).
- `efe8e33` Python scorers/coefficient rules on the web lab (coordinator-only child process).
- `73f6b91`, `8801f8e` file-backed datasets (1 GB / 10M rows, admin limits; 10M rows built in 186 s, 393 MB).
- `238dbd8` OWNER-APPROVED frozen change `es/update.py`: divide by N as the float32 reciprocal (CPU = GPU bits).
- `ff226fd` any GPU machine may coordinate (Windows, small GPU), update-speed estimate in the web.

## Unfinished / not started (resume order)
1. CPU-only coordinator path: "coordinator-only" self-test (update known-answer check instead of text compatibility),
   backend SelfTest branch, exclude such devices from worker selection and from model qualification of the coordinator,
   runner `--device cpu` from the agent config. Nothing written yet.
2. Real Windows coordinator run on Thao's machine: its WSL sshd resets every connection since ~13:25 (needs someone at
   the machine). Windows evidence so far is the recorded worker replay only.
3. eval/compare/serve/worker CLI (plan step 6/7), vLLM probe (step 4), step 8 options (prompt format, boxed scorer, token
   accounting), r11 candidate3 rebuild + full `scripts/check-all.sh`, flag-day checklist (include the live-lab wipe).
4. Publish the Linux CLI installer on a lab download page (built only on the Archive disk, build `lf1-20261020-sysfinish-q1`).

## Live state to clean up
- Isolated lab (port 8790, `.scratch/isolated-lab/start-q1.sh`) and the 5070 Ti packaged worker (`worker5070/start-q1.sh`,
  contribution ON) are RUNNING. Quang's 3060 runs `heteroes-worker run` (ON). Stop: contribution OFF, then quit/SIGTERM
  by PID (never `pkill -f`).
- Flag day note: new workers send `updateSecondsPerSeed`, which an r10 lab rejects; lab and workers must move together.
