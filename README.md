# Hetero-ES-LLM

Reliable ES-based LLM post-training on heterogeneous consumer GPU clusters.

The UI now connects to the separate Track A runtime through a FastAPI backend.
See [runtime setup and supported controls](docs/runtime-integration.md) and
[validation evidence](docs/integration-validation.md).

After installing dependencies and initializing private configuration:

```bash
./start-integration.sh
./stop-integration.sh
```

Real mode is the default. Use `VITE_DATA_SOURCE=mock` for the explicit UI demo.
