# Acceptance GPU matrix and pinned-model preparation

The first local GPU acceptance attempt correctly exposed seven real-Qwen skips under the new zero-skip gate. The
controller and its owned pytest/compile children were stopped by their exact process IDs, before later checks ran.
No acceptance receipt was produced for that aborted batch. Noise/ES completed first: 572 passed, zero skipped,
including the retained real-Qwen model; its raw log is attached.

The diagnostic real-Qwen subset then executed 55 cases and failed one legacy script check because that script requires
the MODEL DIRECTORY itself to resolve to pinned revision 7ae557604adf67be50417f59c2c2f167def9a775. The retained source
is named qwen. The new pytest_gpu_suite wrapper copies its files into a fresh revision-named directory within each
check output, then sets the model environment before pytest imports test modules. No source model file is renamed,
linked for writes or modified. Final real-Qwen subset: 56 passed, zero skipped.

Eight execution test functions (79 parametrized cases) exercise SM120-only TMA projection and attention key staging.
They are now explicitly marked sm120. The 5070 Ti runs all of them. WSL/native 3060 selects 'not sm120', retaining all
portable CPU and SM86 execution tests; these 79 cases are DESELECTED, not passed or silently skipped. Their count is
kept in pytest summaries and receipts. The marker inventory test refuses marking unrelated tests.

Collection matrix:
- Linux suite: 1,636 total; 79 SM120-specific; 1,557 applicable to SM86.
- Native selection: 1,035 total; the same 79 SM120-specific; 956 applicable to SM86.
The WSL and native executed-test floors match those applicable counts, with max_skipped=0. Local retains the independent
last-good floor 1,599 and runs the complete collection. The legacy model-directory guard remains unchanged.

Acceptance selftests: 51 passed; follow-up mutations: 6/6 killed (host floor, environment preparation, revision name,
source-copy isolation, WSL floor, SM120 marker inventory). The initial matrix selftests had three failures before the
host configuration existed. Native Windows additionally matches division/reciprocal bitwise for n=1..4096, 8,192 values.

## What this does NOT show

This is configuration/selection and targeted-model evidence, not final-source full GPU/perf/fault/package acceptance.
The full CPU and GPU acceptance sequence must be repeated after this harness change. SM120 routes are not claimed on
SM86; generic SM86 kernels remain mandatory. Native arithmetic probe alone is not a native product acceptance receipt.
Frozen runtime numerical source did not change in this follow-up; P-FROZEN receipts remain about that same implementation.
