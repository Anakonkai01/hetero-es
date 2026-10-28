# Fault injection run (declared before submission, 23 Oct ~01:00)

Candidate15 on nhan (coordinator + worker), nhut, native Windows 3060. Qwen 0.5B FP32, 24 antithetic candidates,
80 generations, batch 8, validation every 20, seed namespace `overnight-fault-2026-10-23`. Faults by
`fault.py` at completed generations: 6 SIGKILL of nhut's newest worker process; 14 new outbound TCP from nhut's user
rejected (except SSH) for 180 s, then the exact rule removed; 24 `systemctl reboot` of nhut (lingering user service,
keep ON after restart); 34 `taskkill /F /T` of the Windows Worker app, 60 s later a normal relaunch and the switch ON by
UI Automation (the Windows device does not keep ON after restart).

Accept if the run completes all 80 generations, every fault is followed by the member working again (or the reason is
recorded), audits have no mismatch, no worker is quarantined, and an independent replay of the ledger on nhan and on nhut
matches every child hash. Failures are kept with their logs.
