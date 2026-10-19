# M1 lab operations acceptance — 2026-10-10

`validation.json` records sanitized acceptance results for the local Track A/B
implementation. The accepted roadmap and complete delivery record live in the
sibling `Hetero-ES-LLM/docs/lab-roadmap.md` and `docs/m1-implementation.md`.

The runtime full CPU suite passed 2,143 tests with 21 skips. The product backend
passed 45 tests; frontend build/lint and 22 explicit mock behavior groups passed.
Removing workspace isolation and bypassing runtime maintenance were detected by
scratch mutation checks. Migration preserved exact existing experiment, FIFO,
session and password-hash data on a database copy and then the live deployment.

Real browser acceptance covered registration/approval, independent workspaces,
invitation acceptance, owner isolation, session revocation and safe contribution
reassignment. A 3060 job was cooperatively cancelled with a retained checkpoint.
A separate two-GPU N=8/G=3 run finished with 24 accepted results and three published
generations. Both workers confirmed shutdown. These checks demonstrate integration
behavior; they do not establish learning gains or scheduler speedup.

The full-size idle backup contained 33,597,880,320 bytes. Restore into a new
directory preserved historical tables, 16 experiments and 13 checkpoint
references, revoked sessions, held the queue and regenerated runtime credentials
and process/worker directories. A real cold boot on separate ports authenticated
with the preserved password and downloaded the historical checkpoint through the
restored backend/runtime with the original checksum. No GPU jobs were launched.
Auxiliary services were stopped after verification. The original deployment and
historical evidence were preserved. Native browser backup-download authorization
also passed; that download was cancelled immediately to avoid a duplicate 33 GB
archive.

The first full-size campaign exposed unnecessary retention of an intermediate
runtime transfer snapshot. Only that generated, verified transfer copy was
retired; original run evidence and the verified combined archive were retained.
Automatic transfer retirement, cleanup-failure reporting, restoration free-space
preflight and dispatch held through the final checksum were then covered by CPU
regressions. A second full-size archive campaign was not run for those refinements.

Raw databases, screenshots, archives and restored data remain outside Git under
the private deployment directory. No credentials or password hashes are included
here. Previous evidence directories are unchanged. GPU consumption remains within
the original two-hour budget; it was not reset. M2–M6, native installers, public
network deployment and parallel scheduling remain planned. The optional 1660S
was unavailable and was not validated.
