# Web application

React, TypeScript and Vite client for the agent-mode Lab Server API. Requests use the current session and workspace;
there is no mock data mode. Shared components, themes and Vietnamese translations live in `packages/product-ui`.

Run commands from the repository root after `npm ci`:

```bash
npm run build:web
npm run dev --workspace frontend
npm run lint --workspace frontend
npm run test:unit --workspace frontend
```

The supported integration check is `scripts/check-all.sh <fresh evidence directory>`. It starts isolated CPU fixture
labs and exercises browser flows; it does not modify the public lab. See `docs/refactor-handoff.md` for cleanup status.
