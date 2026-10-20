# Research options checkpoint (2026-10-20)

Optional `promptFormat` (`chat` or `raw`) is wired through SDK/spec, product, backend and web. Absence retains the old
recipe identity and chat behavior. Raw prompts bypass the chat template and require a null system prompt.
`boxed-number@1` scores the last plain decimal boxed answer with exact Decimal comparison; malformed final boxes score
zero. An optional formatReward (default 0, finite and at least 0 but less than 1) rewards a valid wrong number.
Nested LaTeX and fractions are deliberately unsupported. Majority extraction supports the same scorer.

Tests were written first (`before.log`). `runtime-final.log` records 37 passing option/document/scorer tests before the
last large-number case; the combined later checkpoint is in `../2026-10-20-usage/checkpoint-final.log`.
Backend, frontend review, TypeScript and i18n checks passed. `mutation-final.log` kills 7/7 mutations listed in
`mutants.json`. The first mutation control could not find an immutable runtime artifact in the scratch copy; no mutations
were attempted in that run. The final control uses self-contained option/document tests.
`first.log` exposed a generic scorer fixture inserting False into the new numeric option; the fixture now uses 0.0 and
an explicit negative test still rejects booleans. Initial TypeScript failures and the successful rerun are retained.

## What this does NOT show

No full check-all run after these changes, final r11 package, real raw-prompt GPU run, learning benefit or public deployment.
The next agent must perform those applicable final system checks before calling the release ready.
