# Overnight follow-up decisions — 2026-10-23

Source: owner responses in the follow-up grilling session for
`handoff-2026-10-23-overnight.md`.

## Settled decisions

- Q1: automatic cleanup may remove reproducible temporary data. Preserve the data
  required for replay, verification and result downloads until the run owner
  explicitly deletes it. Classify artifacts before choosing cleanup behavior;
  completed-run status alone does not make a directory disposable.
- Q2: prioritize host usability, keep systemd-oomd enabled, and diagnose/reduce
  memory pressure before considering special protection for the worker. The owner
  explicitly marked this incident as important. Do not treat successful recovery
  as resolution of the underlying problem.
- Q3: keep the overnight run data on Archive as its primary location. Full checksum
  verification and a read/replay check from Archive remain outstanding; successful
  result-page access and the recorded size/path comparison are limited evidence.
- Q4: defer the real low-disk acceptance exercise to future work. Do not run it as
  part of the current follow-up. Candidate16's low-disk pause remains unaccepted
  under actual disk-pressure conditions.

## Important open incident: systemd-oomd killed the coordinator service

Status: **policy agreed; root cause unresolved; mitigation not implemented**.

**Review 2026-10-23 10:20 ([evidence](evidence/2026-10-23-oomd-review/README.md)):** strong hypothesis = the
recovery-point upload thread (`product/cloud_sync.py`) re-hashing ~3-4 GB per attempt, buffering ~1 GB per upload and
writing ~1 GB every ~2 min to the lab storage on the NTFS/FUSE Archive disk during a 24 s/generation run. Confirmed
separate bug: with the Archive full, the worker service still re-reads ~60 MB/s every 30 s with no run active and holds
9.1 GB of page cache. Five fixes proposed there; none implemented.

On 2026-10-23 at 02:50:07 (journal timestamp), systemd-oomd killed three processes
in nhan's `heteroes-worker.service`. Its parent `user@1000.service` had memory
pressure of 53.10%, exceeding 50% for more than 20 seconds with reclaim activity.
This percentage measures memory-related stall time (PSI), not RAM utilization.
The service's current memory usage was 7.3G; 17.4G memory and 1.4G swap were the
service's lifetime peaks, not measurements at the instant of the kill.

systemd restarted the service at 02:50:22. The coordinator recovered from its
ledger at generation 62, and the run finished 600/600 generations with 720 matched
audits and matching independent ledger replays on nhan and nhut.

**Recovery is bounded:** the current supervisor permits one automatic coordinator
recovery. A second coordinator failure sets the run to `FAILED` with
`Coordinator failed twice`. Service restart must not be described as guaranteeing
continued progress through repeated oomd kills.

Page-cache pressure from weights publication, reads or uploads is a hypothesis,
not an established cause. Recovery points hard-link the weights; a snapshot does
not necessarily create another full weights copy. The soak telemetry sampled
selected processes' RSS every five minutes and did not capture sufficient cgroup
anonymous/file memory, PSI or host-wide state to identify the source of pressure.

Follow-up work:

- [ ] Capture host and service memory/PSI, anonymous and file-backed memory,
  swap and writeback activity around weights/recovery operations to identify the
  source of pressure.
- [ ] Select and validate a mitigation based on those measurements while keeping
  host protection enabled. Do not add `ManagedOOMPreference=avoid`/`omit` or disable
  oomd merely because one restart recovered successfully.
- [ ] Assess how the one-recovery limit affects repeated memory-pressure events;
  changing that limit is not part of the agreed policy.

Evidence and implementation references:

- [Raw oomd journal](evidence/2026-10-23-overnight/soak/oomd-journal.log)
- [Soak outcome and evidence limits](evidence/2026-10-23-overnight/README.md)
- [Coordinator recovery limit](../runtime/src/heteroes/product/run_supervisor.py)
- [Worker service restart policy](../runtime/src/heteroes/product/worker_service.py)
- [Recovery-point hard links](../runtime/src/heteroes/product/recovery.py)
- [Soak telemetry sampler](evidence/2026-10-23-overnight/soak-sampler.sh)

## Deferred verification

Important follow-up from the owner's live-run review: the completed 600-generation
soak has **722 selected audits, 720 completed and matched, and two timeouts at
generation 63**. The missing generation-62 summary after recovery made the old
log-based selection total 719. A successful numerical replay and 720 matched audit
rows must not be described as proof that every selected audit finished. Reporting
is repaired separately; the audit-timeout/recovery behavior remains an open
follow-up. See [the investigation](evidence/2026-10-23-long-run-ui/README.md).

Future low-disk acceptance should use an isolated storage environment, verify a
pause at a generation boundary, free space, resume the run, and check replay
against its recorded hashes. Scope and scheduling are undecided.

This note records decisions only. It does not claim that cleanup, Archive
verification, memory-policy changes or the deferred acceptance test are complete.
