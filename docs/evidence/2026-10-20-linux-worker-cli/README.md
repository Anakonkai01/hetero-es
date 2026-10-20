# Headless Linux Worker CLI and one-line installer (2026-10-20)

`heteroes-worker` (`runtime/src/heteroes/product/worker_cli.py`) does what the desktop Worker does, without a window:
install the pinned Python wheels and model (each SHA-256 checked, `pip --no-index --require-hashes`), run the same
numerical admission (`heteroes.product.qualification` with the shipped reference), pair with a one-time code from the
lab's Devices page, and run the device agent (`desktop_bridge.Bridge`, so stop/drain is the desktop's). Turning
contribution ON/OFF stays on the lab's Devices page. `scripts/build-linux-worker.py` packs the desktop Worker's pinned
resources into a bundle and fills `scripts/install-worker.sh.in` with the bundle and Python checksums.

Checks: `runtime/tests/ledger/test_worker_cli.py` (unit), `backend/tests/test_worker_cli_lab.py` (pairing, approval,
boot and recipe v3 admission through the real lab routes, using the real 5070 Ti v3 self-test), and
`backend/tests/test_linux_worker_installer.py` (the installer run for real against file:// downloads with a fake Python
whose pip is a no-op). Mutation: runtime 9/9 killed, installer/builder 3/3 killed (`mutation-*.txt`).

## What this does NOT show

- No real GPU, real download of the pinned wheels/model, or real WSL; that is the separate 3060 receipt.
- Not published on any lab's download page, and the desktop Worker resources were not refreshed by this commit.
- Turning contribution ON from the web and running assignments are covered by the existing agent tests only.
