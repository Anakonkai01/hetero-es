# r11 v3 wiring and Windows v3 worker admission, full CPU acceptance at d415f68 — 2026-10-19

Handoff `docs/handoff-v3-audit-recovery.md` section 5 steps 4–5, plus the combined acceptance of steps 1–5
(`7d0e8bc` … `d415f68`).

## Changes covered

- `69172f9` (step 4): `qualification.main` runs `qualification_v3.qualify` for a `formatVersion: 3`
  reference, with the adapter resolved beside `reference.json`; the legacy path is unchanged. Desktop setup
  writes the installed profile's name into READY.json (`readyRecord`, refuses a profile without a name)
  instead of a fixed `desktop-v1`. The worker sends v2 **or v3** evidence to `/api/v1/device/qualification`
  only when the lab's health lists one of those versions; a v1-only device or an older lab sends nothing.
- `d415f68` (step 5): `SelfTest` accepts native Windows with `runtimeProfile: desktop-v3` only as a
  worker (`coordinator: false`), advertising exactly `[3]`, with exactly the pinned model hash, PEFT 0.21.2,
  the pinned adapter `051b79e3…` and both reference cells (`recipeV3`, `recipeV3Lora`) passed, repeated,
  exactly restored and equal to the shipped reference's recipe/output/negative-probe hashes
  (`backend/constants.py DESKTOP_V3_REFERENCE`). `v3_qualification` no longer rejects Windows by platform;
  it relies on that validation. The desktop-v1 Windows route and Linux-only v2 are unchanged.
  The backend test feeds the real RTX 3060 result from `../2026-10-19-v3-qualification-reference`.

## Results

- `check-all.log` / `checks/`: **22/22 ALL PASS** at `d415f68`; runtime **2,287 passed, 100 skipped**;
  backend **313 passed**.
- `packaging-check.log`: `scripts/build-apps.sh --check` (Linux unpacked Worker and Lab Server in a fresh
  scratch source copy, shared-module imports) passed.
- `mutation/`: entry-point dispatch 3/3, desktop wiring 5/5, backend admission 14/14 mutants killed (the
  backend list was written after adding cases for `[1]`, an extra model hash, LoRA model hash and LoRA
  `passed`, which are not otherwise caught by the generic v3 rule).
- Earlier steps: `../2026-10-19-v3-lora-cross-os`, `../2026-10-19-v3-qualification-reference`,
  `../2026-10-19-r11-profile-v3` (each with its own mutation receipts).

## What this does NOT show

- No real device enrolled, qualified through the app, approved or given work; no lab state changed; the live
  deployment (`79876cb`, r10) is untouched and `3060-thao` stays REVOKED.
- `desktop/worker/resources/` still holds the r10 desktop-v1 profile; no r11 installer exists yet.
- Browser/Electron probes use disposable fixtures; GPU and native Windows facts come only from the linked
  dated evidence, not from this CPU suite.
