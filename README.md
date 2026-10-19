# Hetero-ES-LLM

Reliable ES-based LLM post-training on heterogeneous consumer GPU clusters.

Current checkout: one repository, with the numerical runtime in `runtime/` and the product at the root.
Cleanup continues on `refactor/cleanup`; read [the current handoff](docs/refactor-handoff.md).
The only supported control path is Lab Server → outbound device agent → coordinator/worker.
The older integration guides linked below are historical; their loopback/SSH launch scripts have been removed.

For the current M3 worktrees, verified Windows trial, private local archive,
service state and next Linux installer test, start with the
[2026-10-11 session handoff](docs/m3-session-handoff.md).

The UI now connects to the separate Track A runtime through a FastAPI backend.
See [runtime setup and supported controls](docs/runtime-integration.md) and
[validation evidence](docs/integration-validation.md).

The accepted next-stage plan is saved in [the M1–M6 roadmap](docs/lab-roadmap.md).
See [M1 implementation status](docs/m1-implementation.md) and
[the lab operator guide](docs/lab-operations.md) for registration/approval,
independent workspaces, GPU contribution and idle backup/restore.

For an initialized agent-mode lab, the CPU server uses an explicit private configuration directory:

```bash
CUDA_VISIBLE_DEVICES='' .venv-backend/bin/python -m backend.server \
  --private /path/to/private-lab --web /path/to/built-web --headless
```

The live workstation lab runs from a separate deployed clone in `~/.local/share/heteroes-lab/app`.
Use its `scripts/local-lab.py` for operations; see [the workstation guide](docs/local-lab-operations.md).

Real mode is the default. Use `VITE_DATA_SOURCE=mock` for the explicit UI demo.
