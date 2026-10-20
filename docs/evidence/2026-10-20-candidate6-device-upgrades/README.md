# Candidate6 isolated lab and installed-device upgrades

Continue the owner-authorized release plan after the separately approved FP32/CPU-reference decoder.
Packages and source receipts: `../2026-10-20-r11-candidate6/`. All four isolated devices were freshly
read as contribution OFF, unallocated; both CLI agents stopped. Public r10 lab remains unchanged.

Upgrade the isolated packaged Lab Server and 5070 desktop Worker, Thao native Windows Worker, Thao
WSL CPU coordinator CLI and Quang WSL GPU CLI. Preserve device identities/private state, verify actual
runtime/source hashes and self-tests. Check C: free bytes before/after installs; do not touch the
Windows original Worker backup. Use the private candidate transport on tailnet port 8802.

Keep contribution OFF through upgrades. Reuse only verified downloads/models. CLI offer scripts must
select the new runtime explicitly, never `ls | head` where old runtime directories may still exist.
Only temporary, stopped test-runtime caches may be replaced to control system-drive usage; preserve
run ledgers, artifacts, settings and credentials. No deletion of historical evidence or user data.

## What this does NOT show

This predeclaration is not a device or 50-generation acceptance receipt. No public installer publication,
live deployment, live approval/revocation or final Windows quit/relaunch/uninstall acceptance yet.
Every irreversible flag-day step still requires the owner's explicit chat confirmation.
