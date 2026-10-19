# Product control plane

Track B's UI/backend is kept in the separate `Hetero-ES-LLM` repository. The
integration adds an optional cancellation hook to `Coordinator` and `WorkerAPI`,
a `CANCELLED` worker terminal state, and the `heteroes.product` control package.
Existing CLI callers retain their previous behavior because the hook defaults to
false. The noise engine, perturbation, restore, coefficient calculation, ledger
commit rules and canonical publication format are unchanged.

The control API uses the standard library and binds to loopback only. It is
versioned through `controlApiVersion: 1` in `/capabilities`; every request requires
the private runtime bearer token. Track B never reads runtime ledger tables.

| Operation | Route | Behavior |
| --- | --- | --- |
| Capabilities | `GET /capabilities` | Pinned model, workloads, workers and supported controls |
| Inventory | `GET /workers` | Cached real GPU probes and reservation state |
| List runtime runs | `GET /runs` | Durable lifecycle state for operational shutdown |
| Accept run | `POST /runs` | UUID hex ID, validated frozen config; idempotent retry |
| Observe | `GET /runs/{id}` | Consistent read-only ledger projection, events and artifact metadata |
| Cancel | `POST /runs/{id}/cancel` | Persistent cancellation marker |
| Download | `GET /runs/{id}/artifacts/{name}` | Allowlisted evidence/checkpoint bytes |

The supervisor starts a coordinator subprocess, publishes a PREPARING recipe,
starts only configured selected workers, and waits for executor readiness before
opening the first generation. Remote commands use configured SSH keys and
administrator-owned paths. Tokens pass via stdin/environment, never argv. A
PID record includes Linux process birth time, so a reused PID is not signalled.
Unknown launch/shutdown ownership holds the GPU reservation. An offline host
whose preflight failed before launch can be excluded without claiming it started.
WSL workers prepend the mounted Windows CUDA libraries and the matching PTX JIT
directory only in their subprocess environment. The matching directory is found
by comparing its gpucomp library with the active mounted copy; WSL exposes the
same Windows file through different device IDs. Stale or ambiguous matches are
not silently selected. No NVIDIA package or existing Python environment is changed.

The runner recovers any already-recorded update before checking cancellation.
Cancellation is checked at cooperative boundaries immediately before recording
an update and before opening another generation. Once recorded, application and
publication run to completion. Workers finish their current candidate's restore
and result handling before exiting. The coordinator HTTP server remains alive
until the supervisor confirms worker shutdown, bounded by a draining timeout.
The supervisor does not grant the next reservation until coordinator and worker
processes are confirmed stopped. One automatic recovery uses the same run ID,
configuration and ledger; a second crash fails the run and keeps the evidence.

Canonical candidate IDs stay in the ledger. The UI projection uses
`{runId}.g{generation}.c{index}` with attempt suffix `.a{number}`. Seeds are decimal
strings, preserving all bits in JavaScript. Projection SQL deliberately omits
lease tokens. Recipe generation-config and workload hashes retain their actual
meaning. Infrastructure failures and lease expiry are never represented as a
reward of zero.

A restore mismatch also enters the persistent control-plane `quarantine.json`.
New runs cannot select that worker; coordinator recovery does not restart it.
Finishing a run or restarting the service never clears this registry. Reuse
requires explicit administrator investigation and a registry update.

See the sibling repository's `docs/runtime-integration.md` for setup, one-command
startup/shutdown, private configuration, supported features and GPU acceptance.
This deployment assumes Linux/WSL and a single product backend process. These
branches are local and await the owner's review; required two-GPU acceptance is
reported separately from CPU tests and one-GPU smoke evidence.
