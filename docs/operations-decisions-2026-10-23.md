# Overnight follow-up decisions — 2026-10-23

Source: owner responses in the follow-up grilling session for
`handoff-2026-10-23-overnight.md`.

## Settled decisions

- Q1: automatic cleanup may remove reproducible temporary data. Preserve the data
  required for replay, verification and result downloads until the run owner
  explicitly deletes it. Classify artifacts before choosing cleanup behavior;
  completed-run status alone does not make a directory disposable.
- Q3: keep the overnight run data on Archive as its primary location. Full checksum
  verification and a read/replay check from Archive remain outstanding; successful
  result-page access and the recorded size/path comparison are limited evidence.
- Q4: defer the real low-disk acceptance exercise to future work. Do not run it as
  part of the current follow-up. Candidate16's low-disk pause remains unaccepted
  under actual disk-pressure conditions.

## Open decision

- Q2: the owner requested a deeper explanation of systemd-oomd before deciding
  whether to change worker protection or memory-pressure handling. No policy has
  been selected.

## Deferred verification

Future low-disk acceptance should use an isolated storage environment, verify a
pause at a generation boundary, free space, resume the run, and check replay
against its recorded hashes. Scope and scheduling are undecided.

This note records decisions only. It does not claim that cleanup, Archive
verification, memory-policy changes or the deferred acceptance test are complete.
