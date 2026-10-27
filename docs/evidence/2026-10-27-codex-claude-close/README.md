# Codex session close for Claude, 2026-10-27

The owner asked to stop and hand work to Claude. The performance goal is paused, unachieved; selected
runtime remains `0eb86cb9` at Qwen short32 9866.13 token/s / 71.315% of the matched vLLM control.
Read the [new handoff](../../handoff-claude-after-codex-perf-2026-10-27.md).

This close adds scope-limited READMEs and hash seals to the eight latest research folders, commits
the evidence in logical groups, and updates the current HANDOFF and local Claude memory pointer.
No additional optimization or GPU test is performed during close. The positive candidates remain
unselected; complete selected-runtime acceptance is the earlier [combined receipt](../2026-10-27-strict-combined-acceptance/README.md).

The evidence groups are committed as `e3a2ae1d` (M64/Newton/MMA), `716d2125` (head tiling/QKV fusion)
and `9224cf08` (three unselected candidates). The following close commit contains this audit and handoff.

`harness/verify.py --out raw/verify-01.json` performs CPU-only checks:

- Every file listed in the eight research seals has the recorded SHA-256, with complete file coverage.
- All retained Python harnesses compile as source text without importing or executing GPU code; JSON parses.
- Final full-pilot harness hashes match their reports, and their token hashes match a retained selected-source control.
- Both attention operator reports identify the final helper source exactly. The READMEs separately state
  the host-only changes after initial operator tests; this audit does not turn those tests into final-suite passes.
- Tracked `runtime/src` bytes equal selected `0eb86cb9`; no untracked runtime source exists.
- Local links in the new handoff, current HANDOFF section and eight evidence READMEs resolve.
- Narrow credential-pattern scans do not detect private keys, bearer credentials or password assignments
  in the closing materials. This is not a general secret-scanning guarantee.

The successful audit covers **85 sealed files**, including **35 Python sources**, **11 JSON documents**
and **8 pilot token-hash cases**, plus **144 unchanged tracked runtime/src files** and **25 local links**.
Current HANDOFF and new handoff formatting are checked with the repository's pinned Prettier. `git diff --check`
is applied to changed Python/Markdown/JSON files. A first unrestricted check reported trailing spaces
inside a retained failed pytest log; raw evidence is preserved verbatim rather than reformatted.
No prior sealed evidence is rewritten. The seal includes this README, the verifier and its result.
The verifier's first attempt assumed every JSON document was an object and stopped on a valid
list-valued mutation specification. The corrected verifier parses both forms; report-specific hash
checks apply to objects. No receipt was written by that failed attempt.

## What this does NOT show

No new runtime implementation, GPU test pass, whole-request gain, fresh ABAB, complete mutation or
cross-host/native/package qualification, learning result, deployment, push/merge or 80% result is
established by closing checks. Existing partial and failed experiment receipts keep their stated scope.
