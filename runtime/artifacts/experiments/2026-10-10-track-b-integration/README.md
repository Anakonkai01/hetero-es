# Track B integration acceptance — 2026-10-10

`validation.json` is the sanitized acceptance summary. The UI/backend repository
is separate: `Hetero-ES-LLM`, based on `claude-design-ui` at
`bcdb71bb773f0239e91c73f915e97f3be96e69a6`. Track A's integration branch is
`feat/track-b-runtime-integration`; Track B's is
`feat/track-a-runtime-integration`. No branch was pushed or merged.

The required 5070 Ti + Quang 3060 campaign accepted 24 candidate results,
17 from the 5070 Ti and 7 from the 3060, and published three generations.
Both workers verified the same recipe and the intermediate replay hashes.
The final checkpoint was downloaded through the authenticated product API and
its SHA-256 matched the published identity. Worker shutdown was confirmed.

Separate real campaigns verified cooperative cancellation, checkpoint retention,
one automatic coordinator recovery, durable FIFO advancement and cancellation of
a queued run before launch. The real browser exercised login, role isolation,
create/start/cancel, candidate seed precision and an authenticated artifact
download. Full CPU tests: 2,138 passed, 21 opt-in model tests skipped. Backend:
15 passed. Frontend build/lint and 22 explicit mock behavior groups passed.

Commands and detailed interpretation are in the sibling repository's
`docs/runtime-integration.md` and `docs/integration-validation.md`.
Original ledgers, weights, private config and browser screenshots are outside git
under `~/.local/share/heteroes-integration/`. This folder contains no credentials
or lease tokens. The optional 1660S was offline and remains unvalidated.

This campaign demonstrates product/runtime integration and lifecycle correctness.
It does not measure learning, scheduler speedup or performance-based admission,
and does not establish high availability or power-loss durability. Earlier runs
that fell back to one selected GPU are explicitly distinguished from the required
two-GPU acceptance. The conservative selected-GPU lifetime bound is 0.177
GPU-hours across nine managed runs; it includes hosts that never started.
