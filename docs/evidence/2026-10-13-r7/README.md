# Evidence 2026-10-13 — r7 release, new web UI, Live view on a real GPU run

Build `lf1-20261013-r7` (Worker + Lab Server, Windows and Linux) and the new web/backend went live on
https://lab.heteroes.site on the evening of 2026-10-13. Everything below was produced by scripts in `scripts/`; nothing was typed by hand.

## What each file shows

| File / folder | What it shows |
| --- | --- |
| `installers-r7.json`, `installers-r7-published.json` | The four r7 installers (sizes and SHA-256) at the prepare step and after publishing into the manifest. |
| `public-verify.json` | Read-only check **from outside, over HTTPS**, after the first web swap: health, home page assets, `/explain`, `/login`, `/register`, `/demo/run.json`, all four installers downloaded in full and matching size + SHA-256, then (admin, password never printed) one finished run's `timeline`, its `/stream` (`timeline` message then `end`, content type `text/event-stream`), notifications and templates. `allOk: true`. `public-verify-before-web-fix.json` is the run before that (same result, earlier web build). |
| `public-verify-final-web.json` | The same check with `--skip-downloads` after the **last** web swap (the installers do not change with the web). `allOk: true`. |
| `worker-packaged-linux/`, `worker-station-packaged-linux/` | The **packaged** Linux Worker (AppImage contents, not the dev build) driven by Electron probes: first-run onboarding and the compact GPU station, signed-out and "Advanced" views. |
| `gpu-live/` | One short **real** GPU run on the RTX 5070 Ti through the public address (`public-route-acceptance.json`: 3 generations × 4 candidates, COMPLETED, worker used the public address, no bulk route, caught up by replay, 12 candidates committed, device restored) and what the browser and the event stream saw while it ran (`live-run.json`: 14 timeline messages, 8 heartbeats, longest silence 15.5 s, `end` received, 0 browser console errors; screenshots `live-starting.png`, `live-running.png`, `live-just-ended.png`). |
| `real-lab-page-audit/` | Read-only audit of **every page of the real lab** (38 page views: all routes × `vi/light/1440` and `en/dark/375`): no horizontal overflow, no console errors; one untranslated string found (`Worker detail`, a page title) and fixed afterwards, then the worker pages re-audited with 0 untranslated (`audit-worker-pages-final.json`). `audit-before-last-two-translations.json` is the run that found it. |
| `checks-final/` | `scripts/check-all.sh`: backend 279 tests, frontend 70, Worker 54, Server 1, product-ui 5, types, lint, i18n (0 missing), web + Worker build, then six browser/Electron contracts against **throwaway fixture labs** (onboarding, Live, experiments, showcase, 36 page views, Worker onboarding, Worker station). **ALL PASS.** |

## What changed in the product (short)

New web UI (language follows the browser; every page reviewed), Live view with SSE and replay, Dashboard control room, compare,
run again, templates, exports (CSV / Markdown / PNG), notifications (bell + opt-in browser), home hero from a real run, `/explain`,
presentation mode, Ctrl+K, compact Worker "GPU station". Details and file map: `docs/session-handoff-2026-10-13-ui.md`.

## What was fixed after the first full check, and how it is covered

1. The real run showed ~60–90 s of "Nothing has run yet" while the GPU loads the model → "Starting up" text (`lib/liveEmpty.ts`; 3 tests, mutation 7/7 killed).
2. A watched run that ended rewound to the start of the replay → it now stays on the finished picture (`replayStart`; test; mutation 6/6 killed; `check-web-live.mjs` step 2b).
3. The first full `check-all` had one failure: the Live probe's selector hit the new "run finished" announcement text (a hidden element). The probe now waits for the experiment link; the whole suite was re-run clean (`checks-final/`, ALL PASS). The first failing log was not kept in the repository.
4. The final audit of the real lab found hover texts and legends of the status tables, and one page title, with no Vietnamese. the missing texts were added and a test now walks every text in `labels.ts` (mutation 5/5 killed); the page title was fixed after the real audit.

## What this evidence does NOT show

- **Nothing ran on Windows.** The Windows installers were built (through Wine) and hashed; the apps were exercised only on Linux/Xvfb. The owner's Windows run of r6/r7 is still the open question (ask for the code in the red box and `%APPDATA%\@heteroes\worker\logs\worker.log` if it fails).
- **`checks-final/` is from before the last two translation changes (item 4; translations only, no logic)**: after them the frontend unit tests (71), product-ui tests (5), `tsc`, `eslint`, `check-i18n` and a real-lab audit were re-run, but not the whole `check-all` again.
- **The packaged r7 apps contain the translation table from before those last additions** (only affects a few web-only texts; the Worker/Server apps do not show them).
- The Live view was recorded with **one** real GPU. The three-GPU picture (home hero, replay tests) is an earlier real run (`d09d6ea8`) replayed.
- The recorded screenshots are from a headless Chromium. The OS-level browser notification pop-up and its permission prompt were not shown on a real desktop.
- The fixture-lab page audit logs two 404 console messages on the Dashboard (the fixture lab lacks device endpoints). The real lab has none (see `real-lab-page-audit/`).
- `public-verify.json` needed one retry in this session: the very first request of one attempt was reset by the peer (a one-off network blip; the second attempt passed). It is not a stability measurement.
- Hours of load or many simultaneous viewers of the stream were not tested (the server limits viewers per process; see `backend/live.py`).
