# Handoff — step 4 done except Quang; step 5 (long 3-GPU run) waits for Quang's C: space (2026-10-20, Claude Sonnet 5.5)

Read `../AGENTS.md`, `plan-r11-release.md` (steps 5–8 open) and `evidence/2026-10-20-candidate5-devices/README.md`.
Branch `feat/v3-audit-recovery`; `main` not yet fast-forwarded. Commits since the last push: `4ab54c6`, `2c524dd`,
`a162cde`, `1c7bedc`, `b29a442`, `e1f074a` and this file (owner runs `! cd ~/projects/heteroes && git push origin --all`; the push still has to be done by the owner because the harness blocks the model).

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

## Quang (updated 21:20, end of the Sonnet session)

- The blocker is gone: after the owner disabled hibernation, Quang's Windows C: has **20 GB free**. The owner allowed deleting
  test data; `heteroes-c3-cpu` and the old `heteroes-worker` were removed from Quang's WSL (used 20 → 9.1 GB; `~/heteroes-venv`
  4.8 GB kept). Details and the C: breakdown: `evidence/2026-10-20-candidate5-devices/README.md` ("Update 21:20").
- The one-line install of candidate5 into `~/.local/share/heteroes-worker` on Quang **was started at 21:09 and may still be
  running or may have been cut when the session ended**. Check `~/.local/bin/heteroes-worker status` on Quang
  (`ssh quang@100.99.227.8`); if it is not installed, start the same command again, it reuses verified downloads in
  `downloads/` (a half-downloaded `.part` file restarts): `curl -fsSL http://100.110.165.40:8801/install-worker.sh |
  HETEROES_DOWNLOADS=http://100.110.165.40:8801 bash` (the private HTTP server, PID 2143087, must still be listening;
  restart: `python3 -m http.server 8801 --bind 100.110.165.40` in the candidate5 `cli` directory on the Archive disk).
  Quang's internet is slow (torch wheel). Record C: free before/after (20 GB now).
- Thao's `worker-system-finish-backup` (5.9 GB, `%APPDATA%\@heteroes`) is the owner's original Worker data; leave it.

## Next (unchanged order)

1. Finish Quang: after the install, `selftest --device cuda` (GPU + `HETEROES_GPU_ACCEPTANCE=1`;
   remember the `LD_LIBRARY_PATH=/usr/lib/wsl/lib` fix), pair with the isolated lab, owner/admin approval via
   `PATCH /api/v1/platform/devices/<id>` with the workspace id; record C: before and after.
2. Step 5 long run (spec and expected checks in the evidence README **before** starting), stop rules apply.
3. Windows quit → relaunch → uninstall on candidate5 once before the flag day; then steps 6–8.

Resume prompt:

> Đọc AGENTS.md, docs/handoff-2026-10-20-quang-then-long-run.md và docs/plan-r11-release.md. Kiểm tra cài candidate5 trên
> máy Quang (đã bắt đầu), self-test GPU, ghép cặp và duyệt, rồi làm bước 5. Tuân thủ các luật dừng. Nói chuyện với tôi bằng tiếng Việt.
