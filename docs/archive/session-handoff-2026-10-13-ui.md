# Session handoff — 2026-10-13 (evening): new web UI, Live view, notifications, GPU station; r7 published

**Read this first**, then `evidence/2026-10-13-r7/README.md` (what each piece of evidence shows and what it does NOT show)
and `session-handoff-2026-10-13.md` (the r6 morning: what the owner still has to try on Windows). Owner rules are
unchanged (`AGENTS.md`): Vietnamese, short, simple; no push/tag, no generated-by or co-author trailers; tests first, then a
scratch mutation check; GPU only with `--gpu` + `HETEROES_GPU_ACCEPTANCE=1`, only the 5070 Ti, short, announced.

## State at the end of this session

- Branch `feat/local-first-lf1` in both repos, commits only on it, nothing pushed. Repo A (runtime) is unchanged.
- **Live lab (https://lab.heteroes.site) runs the new product**: the backend runs from this repo's source (so a restart
  loads whatever is on the branch), the web is `frontend/dist` built from it, and the download page offers **r7**
  (`lf1-20261013-r7`). r5 and r6 files are still on the Archive disk, only the manifest points at r7.
- The database gained two tables (`notifications` read state, `experiment_templates`) created on start-up; nothing else
  in it changed. A copy from before the release (integrity ok, 25 experiments) is in
  `~/.local/share/heteroes-session-archives/2026-10-13-ui-release/product-before-ui-release.sqlite` (mode 0600).
- One real GPU run was made on the 5070 Ti to record the Live view with real data (experiment `8dcda95b…0d7c`, 3
  generations × 4 candidates, about 4.5 minutes, through the public address). Afterwards the device was restored (OFF,
  original private address, no agent, GPU free). It is a fifth "public-route replay-only acceptance" run in the history.
- **Reboot lesson, again**: the machine rebooted at 19:09 and the Archive disk is **not in `/etc/fstab`**, so the lab was
  down ~25 minutes until the disk was mounted by hand (same command as in the morning handoff). `Linger=yes` is set (the
  unit starts at boot) but without the disk the unit only retries every 30 s. The owner has to add, as root:
  `UUID=10443D1F443D094C /mnt/Archive-2tb ntfs-3g uid=1000,gid=1000,umask=077,windows_names,norecover,nodev,nosuid,nofail,x-systemd.device-timeout=10 0 0`

## Owner decisions that shaped this session

Priority audience: the committee that grades the demo (20/11), later the operators and friends. Weekly schedules and freeze
dates were **discarded** ("vibe": the AI decides the scope). Features: compare runs, clone + templates, notifications
(in-web bell + browser only), export for the report, the "feel" of the coordinator handing out work (Live view with
streaming and replay). Languages vi/en in parallel, default from the browser. Keep the design, review every page. Worker
app = compact "GPU station". Extras: animated home hero from a real run, interactive ES explainer, presentation mode,
Ctrl+K. **Deliver once when done**; the AI deploys itself after all checks pass. The 8-character password minimum is the
AI's assumption (the owner only said 12 was too much).

## What exists now (where to look)

| Area | Where |
| --- | --- |
| Languages | `packages/product-ui/src/preferences.ts` (browser default, audit hook), `translations.ts`, `scripts/check-i18n.mjs` (static, fails on a missing/bare string), `frontend/tests/translationsComplete.test.mjs`, `scripts/audit-web-pages.mjs` (every page × language × theme × width, records untranslated strings at run time) |
| Events, artifacts, profile, GPU fleet, operations | `frontend/src/lib/eventText.ts`, `pages/EventsPage.tsx`, `lib/format.ts`, `RuntimePages.tsx` |
| Live view | backend `backend/timeline.py` (pure projection), `backend/live.py` (SSE, heartbeat, viewer limit), routes `/experiments/{id}/timeline` and `/stream`; Caddy `flush_interval -1` in `backend/deployment.py`; web `lib/runFrame.ts` (pure: frame at a time, packets, `replayStart`), `lib/diagramLayout.ts`, `lib/sse.ts` (with polling fallback), `hooks/useRunPlayer.ts`, `components/live/*`, tab `?tab=live` |
| Home hero, Dashboard control room | `components/live/DemoReplay.tsx`, `ControlRoom.tsx`, `frontend/static/demo/run.json` (made by `scripts/export-demo-run.py` from run `d09d6ea8`, names removed) |
| Experiments | compare (`ComparePage`, `lib/compare.ts`), run again, templates (`backend/templates.py`, `lib/templates.ts`, `TemplatePicker`), exports (`lib/exportRun.ts`, `lib/chartExport.ts`) |
| Notifications | `backend/notifications.py` (projection from the audit log and ended runs; follows from server start-up; per-user read state), `/api/v1/notifications`, `NotificationBell`, `lib/notificationText.ts`; browser notifications are opt-in |
| Worker app | `desktop/worker/src/station.ts`, `Station.tsx` (window 820×780), probes `scripts/check-worker-station.cjs`, `check-worker-onboarding.cjs` (both take `--packaged <exe>`) |
| Showcase | `/explain` (`ExplainPage`, `lib/esExplain.ts`), `CommandPalette` (Ctrl+K), presentation mode (`app/presentation*.tsx`, `lib/presentationScenes.ts`, `?present=1`) |
| Whole check | **`scripts/check-all.sh <fresh dir>`**: backend tests, all unit tests, types, lint, i18n, web and Worker build, six browser/Electron probes against throwaway fixture labs. CPU only, never the real lab |
| Public check | `scripts/verify-public-lab.py` (installers size + SHA-256, pages, optional signed-in stream/notifications/templates, read-only), `scripts/record-live-run.mjs` (watch one run from outside: stream messages with arrival times + screenshots) |

## Findings from the real run, and what was done about them

- The stream works through Cloudflare during a live run: 14 timeline messages, 8 heartbeats, longest silence 15.5 s
  (the heartbeat interval), and a clean `end`. The page drew the diagram from the first job on and had no console errors.
- A run spends ~60–90 s in STARTING while the GPU loads the model; the tab used to say "Nothing has run yet". It now says
  "Starting up … loading the model" (`lib/liveEmpty.ts`, tested).
- When the run ended while someone watched, the view rewound to the start of the replay. It now stays on the finished
  picture, paused (`replayStart(…, afterLive)`, tested, plus a step in `check-web-live.mjs`).

- The final read-only audit of the real lab found tooltips/legends in `lib/labels.ts` and one page title without Vietnamese;
  fixed, and `translationsComplete.test.mjs` now walks every text of the status tables. Texts chosen at run time are not
  visible to `check-i18n.mjs`: run `scripts/audit-web-pages.mjs` against the real lab (read-only) after adding pages.

## Not shown / still the owner's

- **Windows**: nothing here ran on Windows. r6 and r7 Windows installers were built (through Wine) and the apps were
  exercised only on Linux/Xvfb. The owner still has to run the Windows Worker from a fresh state; if it fails, ask for the
  code in the red box (e.g. `LAB_UNREACHABLE`) and `%APPDATA%\@heteroes\worker\logs\worker.log`.
- The Live view was recorded with **one** real GPU; the three-GPU picture (home hero, replay tests) comes from an earlier
  real run (`d09d6ea8`) replayed, not from a new multi-GPU run.
- Browser (OS-level) notifications were not shown on a real desktop session: the in-web bell is exercised by the headless
  probes (for example the administrator notification when someone registers), the browser permission prompt and the
  pop-up itself are not.
- The Lab Server (desktop) UI is small and only Linux/Wine tested.

## Next steps

1. Owner: Windows Worker r7 test, fstab line, backend password minimum (8) confirmation, look at the demo flow
   (presentation mode: `?present=1`) and tell what to change.
2. Rehearse the 20/11 demo on the public address: home hero → `/explain` → Dashboard control room → start a short run →
   Live → results → compare. A second GPU (3060 owners) joining a run would make the best live picture; that needs their
   machines and authorisation.
3. Backlog from `session-handoff-2026-10-12-close.md` (identity/epoch, export/restore, graphical network setup) is unchanged.
