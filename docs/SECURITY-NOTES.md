# Findings awaiting an owner decision

These existing behaviors are recorded during the cleanup. They have not been changed because that would change the
product/network policy rather than only its structure and presentation.

| Finding | Evidence in current code | Decision needed |
| --- | --- | --- |
| Public health reveals a private lab address | `routes_inventory.py` returns `privateLabUrl` from `bulkApiUrl`/`apiUrl` without a session. The import UI uses it to link to the private lab. | Decide whether to expose that address, return it only after sign-in, or provide a separate authenticated endpoint. |
| A workstation-specific directory is forbidden in shipped code | `backend/local_storage.py`, `runtime/src/heteroes/product/storage.py` and `desktop/worker/electron/setup.cjs` reject `/mnt/sekai` explicitly. | Decide the configurable storage policy and its migration/installer defaults. The owner rule prohibiting this directory on the workstation still applies. |

No GPU or network policy was changed. Plain HTTP on a private LAN is the existing explicit ADR-006 decision; use the
operator guide and the chosen private network. Installer polish/signing remains separate from this cleanup.
