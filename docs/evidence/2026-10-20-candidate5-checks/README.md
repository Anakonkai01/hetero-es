# candidate5 check suite — 2026-10-20

`scripts/check-all.sh docs/evidence/2026-10-20-candidate5-checks/checks` printed **ALL PASS** (started 20:14 +07, run
alone, CPU only, fixture labs only). It ran on the working tree that the next commit after `cf80a1e` contains: the
step-2 change "surface coordinator agent failures" (see `../2026-10-20-coordinator-failure-surfacing/README.md`).
Only documentation was edited after the run started.

| Step | Result |
| --- | --- |
| runtime-tests | 2482 passed, 102 skipped |
| backend-tests | 374 passed |
| frontend-unit / worker-unit / server-unit / product-ui-unit | 88 / 87 / 1 / 5 passed |
| python-lint, python-format, prettier, source-packages, types, lint | pass |
| i18n | 1072 keys, 0 missing Vietnamese, 0 untranslated text, 0 unused |
| web-build, worker-build | pass |
| web-onboarding, web-live, web-experiments, web-model-qualification, web-showcase, web-pages | pass |
| worker-onboarding, worker-station (Electron under Xvfb) | pass |

`checks/web-experiments/run-that-cannot-start.png` is the new screenshot: a `STARTING` run with the device's waiting
reason as a note and in the Logs tab.

## What this does NOT show

- This is not a candidate5 **build**: no installer was built, prepared or published (plan step 3 is still open), and
  nothing ran on a GPU, on Thao/Quang or on the live lab.
- The browser checks use throwaway fixture labs; the stuck run and its device event are inserted by the fixture.
- Passing these checks says nothing about multi-machine correctness, audits or recovery; the long run (step 5) is open.
