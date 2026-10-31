# Review A4 and follow-up resource regressions

2026-10-31. Acceptance tests: red 10 failures / 33 passes; final 44 passed; mutation 10/10 killed.
A-011: checks require actual pytest counts, GPU suites reject skips, missing summaries fail; mutation results count the
unmodified control, not deliberately failing mutants. Receipts keep counts, summary, final 50 log lines and relative log
paths. Linux minimum 1,599 follows the independent good GPU run; native minimum 1,035 matches collection of the unchanged
native selection. Noise/ES GPU checks are also registered for Linux and native with the pinned real-Qwen path and zero skips.
A-012: documentation is excluded consistently from committed listing and dirty status; rename endpoints are inspected.
A-021: source_tree previously ignored its explicit rev argument and hashed HEAD even while remote staging used another
commit. The regression queries HEAD~1 after a source change and requires the historical identity.

A-022: study reachability and transfer failure leaked OS handles. New tests fail on old code (2 failed), and both mutants
are killed after closing the probe socket and acquiring ownership of the temporary FD before opening the network stream.
The attached study/redirect regression log records the final combined count. New helper tests run on scratch copies using
scripts/mutation-check.py; JSON recipes contain exact mutation edits.

## What this does NOT show

Acceptance harness selftests do not establish product acceptance. Full A6 on the final source, including 3060 WSL/native,
remains pending. Resource probes use socketpair and injected transfer failure, not live lab endpoints. No credentials or
live application state are included.
