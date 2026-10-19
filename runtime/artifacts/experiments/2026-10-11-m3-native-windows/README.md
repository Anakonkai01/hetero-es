# Native Windows Worker hardware evidence — 2026-10-11

Authorized by the owner after installing, approving and enabling the native
Windows Worker. This is actual RTX 3060 / Windows 11 hardware, not Wine or WSL.
The existing Linux 5070 Ti was the coordinator; legacy WSL agents were OFF.

- `native-qualification.json`: authenticated enrollment evidence of two identical
  candidate evaluations plus the 16-answer seed-0 Linux probe, exact weights and
  restore. All 57 Python source file bytes match Track A after path normalization.
  Qualification duration is an owner estimate (<2 minutes), charged as 120 s.
- `distributed.json`: run `95b347701aea49bdbd5b4978d1982a78`, G=2/N=4,
  arith16/hf_generate FP32, canonical CPU noise, alpha=sigma=0.001. Windows committed
  all 8 candidates, performed a fully hash-verified replay and stopped normally.
- `baseline.json`: separate one-GPU Linux run with the same experiment ID and
  numerical settings. Every seed/reward, generation record hash and child hash
  matches. Both runs completed.
- `checkpoint-verification.json`: read and SHA-256 verified the full actual final
  checkpoint files of both runs, each 988,065,536 bytes. Exact byte-checksum match:
  `04934b82565441a60ea7f9e8389b35885cf7066c77d226de3701f625d29e1bb8`.
- `cancel.json`: run `8047b923e2d1427895045b384d130247`, G=2/N=32; requested owner
  OFF during a live lease. CANCELLED after 5 commits, no update published, native
  worker process confirmed dead, all reservations released. Larger N only kept
  work available for the OFF test.
- `final-state.json`: dispatch held, empty queue/reservations, temporary local
  coordinator OFF/stopped; Windows restored to the owner's original ON preference.
- `budget.json`: this trial charged at most 0.116036 GPU-hours, M3a 0.123133/0.25
  including its prior unintended run, cumulative upper bound 1.144965/2.0.
  Full reservation wall time is charged for both GPUs, baseline for one GPU;
  M2's 0.083799 cloud reserve is unchanged.

Raw logs, device tokens, SQLite databases and weights remain outside Git. The
operator runner is B's `scripts/check-native-windows.py`; GPU phases require both
an explicit flag and environment opt-in. Read-only status is the default.

Unverified: clean-image installation without existing development tools, native
single-instance/tray/restart-OFF/Quit, worker networking and coordinator outages.
This evidence qualifies this tested hardware/software combination only. It does
not establish general Windows portability, cloud acceptance or LLM quality.
