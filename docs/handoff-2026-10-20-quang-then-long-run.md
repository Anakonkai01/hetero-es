# Handoff — step 4 done except Quang; step 5 (long 3-GPU run) waits for Quang's C: space (2026-10-20, Claude Sonnet 5.5)

Read `../AGENTS.md`, `plan-r11-release.md` (steps 5–8 open) and `evidence/2026-10-20-candidate5-devices/README.md`.
Branch `feat/v3-audit-recovery`; `main` not yet fast-forwarded. Commits since the last push: `4ab54c6`, `2c524dd`,
`a162cde`, `1c7bedc`, `b29a442`, `e1f074a` and this file (owner runs `! cd ~/projects/heteroes && git push origin --all`).

## State (all on candidate5, isolated lab only; public lab untouched)

- Isolated Lab Server running (`.scratch/isolated-lab/start-c5.sh`, port 8790), 5070 Ti desktop Worker running
  (`worker5070/start-c5.sh`, commands via `commands.jsonl`), both started with `nohup setsid`. Stop them with SIGTERM to
  the PIDs in `isolated-lab/state.json` and `worker5070/driver.pid` (never `pkill -f`).
- Thao WSL CPU coordinator home `~/.local/share/heteroes-c4-cpu` (now candidate5, device `47e0546d`, approved).
- Thao native Windows Worker (candidate5) is running, device `8f3d6919` (`desktop-9f9da13f0f82`), approved, contribution OFF.
  Helpers: `.scratch/windows-system-finish/action.py <action>` (do NOT run `launch` in a foreground pipeline: the
  detached app keeps the SSH pipe open; the app is already up).
- A private HTTP server for the one-line CLI install is listening on `100.110.165.40:8801` (PID 2143087, serves
  `/mnt/Archive-2tb/heteroes-local/downloads/lf1-20261020-r11-candidate5/cli`); stop it by that PID when done.
  Install command: `curl -fsSL http://100.110.165.40:8801/install-worker.sh | HETEROES_DOWNLOADS=http://100.110.165.40:8801 bash`.

## Blocker

Quang's Windows C: shows **6.9 GB free** (same as before). The plan needs ≥ 20 GB before installing the GPU worker
(`df -h /mnt/c` from WSL, or PowerShell `Get-PSDrive C`). Do not install on Quang until it does. Quang's WSL still has
`heteroes-c3-cpu` (8.4 GB, candidate4) and `heteroes-worker` (2.2 GB, old). Thao's `worker-system-finish-backup`
(5.9 GB under `%APPDATA%\@heteroes`) is the owner's original Worker data; leave it unless the owner says otherwise.

## Next (unchanged order)

1. When Quang's C: ≥ 20 GB: one-line CLI install as GPU worker, `selftest --device cuda` (GPU + `HETEROES_GPU_ACCEPTANCE=1`;
   remember the `LD_LIBRARY_PATH=/usr/lib/wsl/lib` fix), pair with the isolated lab, owner/admin approval via
   `PATCH /api/v1/platform/devices/<id>` with the workspace id; record C: before and after.
2. Step 5 long run (spec and expected checks in the evidence README **before** starting), stop rules apply.
3. Windows quit → relaunch → uninstall on candidate5 once before the flag day; then steps 6–8.

Resume prompt:

> Đọc AGENTS.md, docs/handoff-2026-10-20-quang-then-long-run.md và docs/plan-r11-release.md. Kiểm tra ổ C: máy Quang;
> nếu ≥ 20 GB thì cài GPU worker candidate5 cho Quang rồi làm bước 5. Tuân thủ các luật dừng. Nói chuyện với tôi bằng tiếng Việt.
