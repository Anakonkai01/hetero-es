# HeteroES

An Evolution Strategies runtime for evaluating and post-training language models on heterogeneous consumer GPUs,
with a CPU Lab Server, web interface and Electron Worker/Server apps. The system evaluates and records candidates,
applies reproducible updates and supports replay across qualified devices. Both original Git histories are retained.

## Start here

- [Documentation map](docs/README.md) (what to read, where)
- [Current state, decisions and handoff](docs/HANDOFF.md)
- [Contributor and agent rules](AGENTS.md)
- [Vietnamese quickstart for the published r10 installers](docs/guides/quickstart-vi.md)
- [Workstation lab operations](docs/guides/local-lab-operations.md)
- [Backend architecture and data ownership](docs/design/lab-server-architecture.md)
- [Numerical contract](runtime/docs/numerical-contract.md)
- [Evidence index](docs/EVIDENCE-INDEX.md) (evidence, raw artifacts and old session records live on the branch `evidence-archive`)
- [Recorded security/policy findings](docs/SECURITY-NOTES.md)

## Repository layout

| Path | Responsibility |
| --- | --- |
| [`runtime/`](runtime/README.md) | Numerical core, strict engine (`heteroes/strict/`), ledger, coordinator, device agent, qualification |
| `backend/` | HTTP adapters, services, repositories, database transactions and object storage |
| [`frontend/`](frontend/README.md) | Web UI using the real API |
| `desktop/worker`, `desktop/server`, `desktop/shared` | Electron apps and shared download/process utilities |
| `packages/product-ui/` | Shared UI, themes and Vietnamese translations |
| `scripts/`, `deploy/` | Development checks, packaging and local lab operations |
| `acceptance/`, `docs/acceptance/` | `scripts/accept.py` checks, gates M0–M6 and their receipts |
| branch `evidence-archive` | Dated evidence, raw runtime artifacts and superseded documentation ([index](docs/EVIDENCE-INDEX.md)) |

The combined `all` role supports the local SQLite and filesystem deployment. The split `api`, `devices`, `storage`
and `scheduler` roles share PostgreSQL. OIDC and S3/MinIO can be configured independently of numerical execution.
The Server package includes a CPU-only runtime subset. Existing `cloud_*` SQLite names and recovery wire fields
preserve compatibility with stored data and r10 devices.

## Development and checks

Use the Node version in [.nvmrc](.nvmrc), a Python 3.12 backend virtual environment, the qualified `heteroes-match` runtime environment, Playwright
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

See the [frontend README](frontend/README.md) for the Vite proxy and CPU fixture setup.

The packaging check builds both Linux apps unpacked in an isolated source copy and imports their shared modules from
ASAR. It does not publish installers or replace the source checkout's resource profiles. Formatting-only changes can be
hidden in blame with `git blame --ignore-revs-file .git-blame-ignore-revs <file>`.

## Live lab

The public lab is installed at `~/.local/share/heteroes-lab/app` at `10457f9a`, with its own backend environment.
The last published installer line is r10. See the [current status](docs/HANDOFF.md#phiên-bản-và-trạng-thái) and
[workstation guide](docs/guides/local-lab-operations.md) before connecting or operating the service.
