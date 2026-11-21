# HeteroES numerical runtime

The runtime implements deterministic noise and ES updates, candidate leases and audit, model evaluation, and
coordinator/worker execution. Product code at the repository root uses its CPU-safe interfaces for study contracts,
device admission and telemetry.

## Choose how to run

| Workflow | Guide |
| --- | --- |
| Run Recipe v3 locally or on standalone worker processes | [Recipe v3 CLI and Python SDK](docs/v3-local-runs.md) |
| Submit to a workspace on a managed lab | [SDK guide](../docs/design/plan-sdk-lab-bridge.md) and [researcher notebook](notebooks/researcher.ipynb) |
| Use a CPU coordinator with qualified GPU workers | [CPU coordinator](docs/cpu-coordinator.md) |
| Inspect the exact arithmetic, decoder identities and replay contract | [Runtime documentation](docs/README.md) |
| Run probes, build datasets or inspect recovery records | [Runtime scripts](scripts/README.md) |

## Verify on CPU

Run from `runtime/` with Python 3.12 or later and the project's qualified environment:

```bash
CUDA_VISIBLE_DEVICES='' PYTHONPATH=src "$HOME/miniforge3/envs/heteroes-match/bin/python" -m pytest -q
```

Keeping that working directory lets subprocess fixtures resolve the Worker script. The full integration procedure and
GPU authorization rules are in the [root README](../README.md) and [AGENTS.md](../AGENTS.md).

See [current state](../docs/HANDOFF.md), [acceptance by source](../docs/acceptance/README.md),
[third-party sources](THIRD_PARTY.md) and the [evidence index](../docs/EVIDENCE-INDEX.md) for recorded experiments and
archived MASTER/STATUS files.
