# HeteroES web application

React, TypeScript and Vite render the Lab Server UI. The client calls the real API and uses the active user session and
workspace. Shared UI, themes and Vietnamese translations live in [packages/product-ui](../packages/product-ui).

## Development

From the repository root, use the Node version in [`.nvmrc`](../.nvmrc) and install dependencies with `npm ci`.

```bash
npm run dev --workspace frontend
npm run build:web
npm run lint --workspace frontend
npm run test:unit --workspace frontend
```

Vite listens on `127.0.0.1:5173` by default. It proxies `/api` to a local backend at `127.0.0.1:8000`.
Set `HETEROES_BACKEND_HOST` and `HETEROES_BACKEND_PORT` if the backend listens elsewhere.
See [isolated development lab setup](../docs/guides/local-lab-operations.md#isolated-development-lab).

To try the built UI with temporary data, start the repository's CPU fixture on a free loopback port:

```bash
npm run build:web
CUDA_VISIBLE_DEVICES='' .venv-backend/bin/python scripts/serve-test-lab.py \
  --web frontend/dist --port 18117
```

The fixture provides temporary accounts and sample devices. It deletes its state when stopped. For OIDC and deployments
under a subpath, see [OIDC web configuration](../docs/design/oidc-authentication.md).

## Verification

Run `scripts/check-all.sh .scratch/checks-YYYY-MM-DD-name` with a fresh output directory for the integration suite.
The suite builds the frontend and runs browser checks against a temporary lab. See the [project README](../README.md)
for prerequisites and [HANDOFF](../docs/HANDOFF.md) for the workstation lab.
