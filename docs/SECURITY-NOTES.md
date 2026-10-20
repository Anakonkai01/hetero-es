# Findings awaiting an owner decision

These existing behaviors are recorded during the cleanup. They have not been changed because that would change the
product/network policy rather than only its structure and presentation.

| Finding | Evidence in current code | Decision needed |
| --- | --- | --- |
| Public health reveals a private lab address | `routes_inventory.py` returns `privateLabUrl` from `bulkApiUrl`/`apiUrl` without a session. The import UI uses it to link to the private lab. | Decide whether to expose that address, return it only after sign-in, or provide a separate authenticated endpoint. |
| A workstation-specific directory is forbidden in shipped code | `backend/local_storage.py`, `runtime/src/heteroes/product/storage.py` and `desktop/worker/electron/setup.cjs` reject `/mnt/sekai` explicitly. | Decide the configurable storage policy and its migration/installer defaults. The owner rule prohibiting this directory on the workstation still applies. |

## Accepted risk: researcher Python code on the coordinator (owner, 2026-10-20)

The web lab accepts a researcher's Python scorer and coefficient rule (ADR-008 "Owner answers (2026-10-20)"). The code
runs on the experiment's coordinator device with the permissions of that device's user; the device may belong to
another lab member. Safeguards are non-blocking: a child process with a time limit (a hang or crash fails the run
loudly), no `HETEROES_*` credentials in its environment, the code frozen by SHA-256 with the experiment and visible
in it, an audit entry per file, and workers that never receive it. Anyone who offers a device as a coordinator
should treat lab members' code as code they run themselves.

No GPU or network policy was changed. Plain HTTP on a private LAN is the existing explicit ADR-006 decision; use the
operator guide and the chosen private network. Installer polish/signing remains separate from this cleanup.
