A failed attempt, kept because the files show the failure: the firewall (ufw) of the 5070 Ti dropped the packets to port 8765 on the direct
cable, so the worker of the 1660S only saw timeouts (its log has no step, only `waiting_for_coordinator` events) and the 5070 Ti worker did all 24
candidates. The result is still EQUAL to the reference, as it should be. Fixed by a ufw rule; the rerun is
`../2026-10-06-g3-two-machines-cable`.
