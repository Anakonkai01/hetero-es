# Findings awaiting an owner decision

The storage-path policy and the research coordinator trust model are recorded here.

| Finding                                                       | Evidence in current code                                                                                                                      | Decision needed                                                                                                                                          |
| ------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------- |
| A workstation-specific directory is forbidden in shipped code | `backend/storage/local_backend.py`, `backend/storage/s3_backend.py`, `runtime/src/heteroes/product/storage.py` and `desktop/worker/electron/setup.cjs` reject `/mnt/sekai` explicitly. | Decide the configurable storage policy and its migration/installer defaults. The owner rule prohibiting this directory on the workstation still applies. |

## Resolved: the private lab address is for members only (owner, 2026-10-21)

The public `/api/v1/health` no longer returns `privateLabUrl`. A signed-in workspace member gets it from
`/api/v1/capabilities`, which the dataset import page now reads (`backend/tests/test_private_address.py`).

## Accepted risk: researcher Python code on the coordinator (owner, 2026-10-20)

The web lab accepts a researcher's Python scorer and coefficient rule (ADR-008 "Owner answers (2026-10-20)"). The code
runs on the experiment's coordinator device with the permissions of that device's user; the device may belong to
another lab member. Safeguards are non-blocking: a child process with a time limit (a hang or crash fails the run
loudly), no `HETEROES_*` credentials in its environment, the code frozen by SHA-256 with the experiment and visible
in it, an audit entry per file, and workers that never receive it. Anyone who offers a device as a coordinator
should treat lab members' code as code they run themselves.

ADR-006 permits HTTP on a private LAN. Follow the [workstation guide](guides/local-lab-operations.md) for the deployed lab.
