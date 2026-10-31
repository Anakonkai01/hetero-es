# Part A native Windows GPU acceptance at src-ede4338e

Source identity: `src-ede4338ef54a443a0ecc33a2bc96ea836ea188b856727ed63e095594a7b8b3a4`, commit 21d7f591.
The committed runtime/acceptance tree was staged with git archive and executed on the RTX 3060 under native Windows.
All three selected checks passed on 2026-11-01. Every copied check log was verified against the receipt SHA-256.

- noise-es-gpu-native: 572 passed, zero skips; real pinned Qwen model enabled.
- strict-gpu-suite-native: 956 passed, zero skips; 79 SM120-only execution cases explicitly deselected on SM86.
- strict-parity-qwen-native: PASS against the shared strict golden hashes.

The source identity matches the separately archived CPU receipt. Architecture deselection is recorded as deselection,
never as a pass or skip. No unrelated test exclusion was added.

## What this does NOT show

This does not prove SM120-specific TMA kernels on SM86, Linux/WSL performance, a deployed lab, PostgreSQL/OIDC/MinIO,
MiniCloud operation, other GPUs or a learning outcome. Local and WSL acceptance on this source remain separate checks.
