# G6: a download that breaks off and is resumed (07/10/2026)

`failure_campaign.py --scenarios cut-link --candidates 32 --generations 4 --cut-seconds 15 --cut-delay 3 --worker-http-timeout 8`, FP32 chunk 16, lease 20 s. N = 32 makes a generation last about 45 s on the 5070 Ti, longer than the cut, and the workers' HTTP timeout is 8 s so that the
cut breaks the transfer. The packets from the 1660S were dropped 3 s after generation 0 was published, in the middle of its download of the new weights, for 15 s.

What the log of the 1660S shows (`cut-link/worker-1660s.jsonl`):

- `transport_error`: "the download of 443f15823ec6 broke off: timed out" (the read timeout of 8 s); the partial file `.partial-<sha256>` was kept;
- the next `sync` event: **`resumed_from_bytes` 325,058,560, `downloaded_bytes` 663,006,976** (together the 988,065,536 bytes of the file), `transfer_seconds` 6.9: the worker asked for `Range: bytes=325058560-`, the coordinator answered 206 with the rest, the SHA-256 of the whole was checked and it was accepted;
- later syncs of the next generations are full transfers (`resumed_from_bytes` 0, 8.5 s) as usual; the 1660S then evaluated 14 candidates and exited with `finished`.

The experiment ended with **the same weights as the undisturbed reference** (`f09bf0ad...`, `reference/`); 128 results, none twice. This is the resumable download of `tests/ledger/test_http_hardening.py` seen on the two real machines, once. Not shown: a partial file that is corrupt (the unit tests do that), other cut lengths.
