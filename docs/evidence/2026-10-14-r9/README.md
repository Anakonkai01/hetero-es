# Evidence 2026-10-14 — Worker r9: name the network failure

Build `lf1-20261014-r9` (Worker + Lab Server, Windows and Linux) is on the download page of https://lab.heteroes.site.
Backend and web are unchanged. r8 and older files stay on the Archive disk; only the manifest points at r9.

## Why
With r8 the owner could not sign in on Windows: "The lab did not answer ... LAB_UNREACHABLE". The lab was healthy from
outside (HTTP 200) and had been up since 12:59. The app turned every network exception into the same code and logged
nothing, so the cause (DNS, certificate, firewall, proxy) was invisible. The real cause on that PC is still unknown.

## What changed (desktop/worker)
- `service.cjs`: `networkCode()` maps Node's system error code (`error.cause.code`) to `LAB_DNS_FAILED`,
  `LAB_CONNECTION_REFUSED`, `LAB_CONNECTION_RESET`, `LAB_TIMEOUT`, `LAB_NETWORK_DOWN`, `LAB_CERTIFICATE_REJECTED`; unknown
  failures keep `LAB_UNREACHABLE`. One `network error` log line per cause + host (host, route and cause only; never a body or token).
- `main.tsx`, `translations.ts`: plain vi/en sentence for each code.
- `scripts/check-worker-onboarding.cjs`: a closed port is now expected to show `LAB_CONNECTION_REFUSED` (was `LAB_UNREACHABLE`).

## Files
| File | Shows |
| --- | --- |
| `checks/` | `scripts/check-all.sh`: ALL PASS (Worker 71 tests incl. 6 new in `lab-network.test.cjs`, types, lint, i18n, builds, six browser/Electron probes on throwaway fixture labs). |
| `worker-packaged-linux/`, `worker-station-packaged-linux/` | The packaged Linux Worker driven by the onboarding and station probes. |
| `installers-r9.json`, `installers-r9-published.json` | Sizes and SHA-256 of the four installers, prepared then published. |
| `public-verify.json` | Read-only check over HTTPS: pages, all installers downloaded and matching size + SHA-256, `allOk: true`. |

Scratch mutation check: 9 mutants (DNS / certificate / reset not mapped, cause ignored, log every time, no log, route not
logged, always the general code, connect route lost) all killed; one survivor on the first run led to an extra assertion.

## What this does NOT show
- Nothing ran on Windows. This build only makes the cause readable; it does not fix the connection.
- If the cause is that Node's fetch ignores the Windows proxy / certificate store, the fix (Electron's `net.fetch`) is not
  in this build; it needs the owner's log first.
