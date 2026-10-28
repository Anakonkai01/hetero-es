# HeteroES

An Evolution Strategies runtime for evaluating and post-training language models on heterogeneous consumer GPUs,
with a CPU Lab Server, web interface and Electron Worker/Server apps. This repository contains both original Git histories.
The project demonstrates runtime, ownership and replay behavior; passing infrastructure checks is not evidence of learning gains.

## Start here

- [Current state, decisions and handoff](docs/HANDOFF.md)
- [Contributor and agent rules](AGENTS.md)
- [Vietnamese quickstart for r10](docs/quickstart-vi.md)
- [Live workstation operations](docs/local-lab-operations.md)
- [Numerical contract](runtime/docs/numerical-contract.md)
- [Evidence index](docs/EVIDENCE-INDEX.md) (evidence, raw artifacts and old session records live on the branch `evidence-archive`)
- [Recorded security/policy findings](docs/SECURITY-NOTES.md)

## Repository layout

| Path | Responsibility |
| --- | --- |
| `runtime/` | Numerical core, strict engine (`heteroes/strict/`), ledger, coordinator, device agent, qualification |
| `backend/` | CPU API, identity, queue, reservations, recovery storage and metadata backup |
| `frontend/` | Web UI using the real API |
| `desktop/worker`, `desktop/server`, `desktop/shared` | Electron apps and shared download/process utilities |
| `packages/product-ui/` | Shared UI, themes and Vietnamese translations |
| `scripts/`, `deploy/` | Development checks, packaging and local lab operations |
| `acceptance/`, `docs/acceptance/` | `scripts/accept.py` checks, gates M0–M6 and their receipts |
| branch `evidence-archive` | Dated evidence, raw runtime artifacts and superseded documentation ([index](docs/EVIDENCE-INDEX.md)) |

Backend telemetry and study contracts import the CPU-safe runtime modules directly. The Server packager selects their
small dependency set; importing the Server does not load torch. Existing `cloud_*` SQLite names and recovery wire fields
are retained for compatibility with stored data and r10 devices. Local recovery uses filesystem storage.

## Development and checks

Use Node 24, a Python 3.12 backend virtual environment, the qualified `heteroes-match` runtime environment, Playwright
Chromium and Xvfb. From the repository root:

```bash
python3 -m venv .venv-backend
.venv-backend/bin/python -m pip install -r backend/requirements-dev.txt
npm ci
scripts/check-all.sh .scratch/checks-YYYY-MM-DD
```

The output directory must be fresh. The command runs runtime/backend tests, Python lint/format, Prettier, source-package
imports, web/app unit tests, types, i18n, builds and fixture browser/Electron flows. It never starts a real GPU job.
Override `RUNTIME_PYTHON`, `PYTHON` or `RUFF` if the qualified environments are installed elsewhere.

```bash
npm run build:web
npm run build:worker
scripts/build-apps.sh --check .scratch/my-fresh-linux-check
```

The packaging check builds both Linux apps unpacked in an isolated source copy and imports their shared modules from
ASAR. It does not publish installers or replace the source checkout's resource profiles. Formatting-only changes can be
hidden in blame with `git blame --ignore-revs-file .git-blame-ignore-revs <file>`.

## Live lab

The public lab runs from `~/.local/share/heteroes-lab/app`, a separate deployed clone with its own backend environment.
It is independent of this working tree. Operate it through its `scripts/local-lab.py`; never start another controller
against its database or kill its processes manually. The currently published build remains r10.

Historical setup commands are under `docs/archive/` on the branch `evidence-archive`; use the current operator guide for the supported agent path.
