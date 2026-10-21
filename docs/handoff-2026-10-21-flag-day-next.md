# r11 is LIVE; flag-day smoke run and close-out left; next session starts with the owner's GSM8K notebook

Checkpoint 2026-10-21 ~21:20 +07, branch `feat/r11-scheduling-elastic`, origin `main` = release `93ff85f`. Evidence of the
whole day: `evidence/2026-10-21-r11-flag-day/README.md` (steps A-D, port fix, rollback). Supersedes
`handoff-2026-10-21-candidate9-run-result.md`.

## Done today

- Candidate9 accepted by the owner's option (a) after the `greedy-tail` replay (`evidence/2026-10-21-restart-run-candidate9/`).
- Release step 6: `main` fast-forwarded to `93ff85f` and every branch pushed (`evidence/2026-10-21-release-step6/`).
- Thao Windows uninstall test and cleanup of the earlier sessions' leftovers (`evidence/2026-10-21-windows-uninstall-candidate9/`).
- Flag day: verified Archive backup `/mnt/Archive-2tb/heteroes-local/backups/r11-flag-day-20261021/`; live lab stopped, r10
  database set aside (`state/product-r10-before-r11-20261021.sqlite`), live copy at `93ff85f` with the candidate9 web build,
  fresh database with only `admin` (simple password by the owner's choice; never write it in the repo); candidate9
  installers published and verified through the public URL; public compute route moved to the coordinator port 8765.

## Live state now

| Device | Kind | State |
| ------ | ---- | ----- |
| `5070ti-nhan` (`cli-71b757062fd9`) | CLI, `--coordinator --host 100.110.165.40`, home `~/.local/share/heteroes-worker` | approved, ON; `heteroes-worker run` in the owner's terminal |
| `3060-thao` (`desktop-d9017660e75f`) | Windows desktop app, data on `F:` | approved, ON; **Tailscale disconnected on Windows** (public-route test) |
| `quang-3060` (`cli-73b87e369ddc`) | CLI in WSL, `LD_LIBRARY_PATH=/usr/lib/wsl/lib` | approved, ON; `nohup` agent, log `~/heteroes-live-run.log` |
| `1660s` (`cli-d90d1da024e9`) | CLI | approved, ON; `nohup` agent, log `~/heteroes-live-run.log` |
| `5070ti` (`cli-e87612dfcb9a`) | first pairing without `--coordinator` | REVOKED |

Contribution resets to OFF on every boot. No experiment exists on the live lab yet.

## Left of the release plan

1. **Step 7.4/7.5 smoke run:** a short managed run (2 generations, audits on) with coordinator `5070ti-nhan`, verified for exact
   parity like candidate9 (`verify_managed_run.py` on a copy of the coordinator ledger under the 5070's CLI home `runs/`). It is
   also the **first r11 test of the public compute route**: Thao must reach the coordinator through `https://compute.heteroes.site`
   (replay-only). Unproven until this run: whether the replay-only route carries a v3 full-weight run end to end.
2. **Step 8 close-out:** make `docs/HANDOFF.md` the single entry point and move superseded handoffs to `docs/archive/`; stop
   the isolated lab (port 8790) and installer HTTP (8802); delete old CLI homes (Thao WSL `~/.local/share/heteroes-c4-cpu`,
   `heteroes-power`, `/tmp/heteroes-r11-c9*`), then compact Thao's and Quang's WSL `ext4.vhdx`; remove
   `frontend/dist-r10` from the live copy once r11 is trusted. Ask before each deletion.

## Product findings of the day (backlog, none fixed)

1. Linux desktop Worker tarball fails to start on the 5070 (owner report; get the exact message).
2. CLI downloader: no retry on transient network errors (`handshake operation timed out`, `Remote end closed connection`)
   and no progress for large files; Linux needs 56 wheels (CUDA split) against 39 on Windows.
3. CLI has no "forget pairing" and no rename; a device name is fixed at `join`.
4. `join` without `--coordinator` gives `host 127.0.0.1` silently; easy to pair the intended coordinator wrongly.
5. `local-lab.py` fails with `OperationalError` on a missing product database (fresh install / after a wipe).
6. The lab's `privateComputeUrl` and the coordinator port (fixed 8765) can drift apart (r10 had 8769); the public compute
   route reaches only a coordinator on the lab machine, one at a time.
7. `greedy-tail` keeps a slow member's single speed sample forever and never logs declines (c9 analysis).
8. Owner: the web experiment page is too hard to use.

## Next session (owner's request)

Build a professional **notebook for GSM8K**, written for an experimenter/scientist, driving the live lab. The owner asked
to be **grilled first** (several question rounds, explain terms from basics) before any plan or code. Remember the
owner's earlier rule: the project claim is the system, not "ES learns"; no GPU-days on learning runs without the owner's
explicit choice. The smoke run above can be done from that notebook if the owner agrees.
