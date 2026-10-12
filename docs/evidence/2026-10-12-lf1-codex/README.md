# LF-1 continuation: coordinator selection and route diagnostics

Local branch `feat/local-first-lf1`. The public lab and its r4 installers were not
restarted or republished for these checks. No GPU, SSH or system configuration work.

## Checks

- `worker-tests.txt`: Node service, setup, vault and real Python bridge tests.
- `backend-tests.txt`, `runtime-tests.txt`: complete CPU suites (counts in the files).
- `worker-mutants.json` / `worker-mutation.txt`: ten deliberate faults in role,
  address, ownership and pending-configuration handling, all detected.
- `backend-mutants.json` / `backend-mutation.txt`: six faults in transactional role
  updates and ownership guards, all detected.
- `runtime-mutants.json`: eight transport/diagnostic faults. The first run
  (`runtime-mutation.txt`) missed two faults. Tests were extended to inspect the
  socket until EOF and reject a 200 response even with correct range headers;
  `runtime-mutation-final.txt` is the rerun. See the final file for results.
- `ui/worker-ui.json`: first Electron UI check with a CPU HTTP fixture and synthetic
  qualification, plus screenshots at 1280, 780 and 360 px.
- `ui-final/worker-ui.json`: final UI, including pending-role confirmation after
  login. Its screenshots reflect the final displayed check messages. Fixtures use
  no real account, device token or GPU qualification.

`tests/ledger/test_connection_check.py` in Track A also exercises a real authenticated
`CoordinatorServer` on loopback with a synthetic weights file. It reads exactly 64
bytes with a bounded range, refuses a wrong grant, does not request work, refuses
redirects, and labels public fallback as replay-only without requesting weights.

## What this does NOT show

- No GPU coordinator or worker job ran with the new desktop flow. A synthetic
  qualification proves UI/service selection rules, not numerical compatibility.
- No second machine, different physical network or native Windows installation.
- No ordinary person's desktop walkthrough. Screenshots use Xvfb.
- No new public release: the running lab still uses the previous deployment.
  A paired device requires the new backend configuration capability before changing
  its role. Automatic public-compute tunnel wiring for a new coordinator is not built.
- Connection checks measure reachability and a short byte range at that moment;
  they do not prove bandwidth, long-run stability or full-file checksum validity.
- Mutation checks target the listed faults. They are not exhaustive and do not
  prove all possible failures are covered.

Commands: `node --test desktop/worker/tests/*.test.cjs`; the CPU commands in
`AGENTS.md`; `CUDA_VISIBLE_DEVICES='' xvfb-run -a node scripts/check-worker-ui.cjs <fresh-output>`.
Mutation commands use `scripts/mutation-check.py` on scratch copies, with `NODE_PATH`
for Node tests and `PYTHONPATH=src` / `CUDA_VISIBLE_DEVICES=''` for Track A.

## Subsequent control checks

`control-mutants.json` / `control-mutation.txt`: seven admission/reconcile and
protocol faults, all detected. `agent-header-mutants.json` /
`agent-header-mutation.txt`: omission of the agent header, detected. The protocol
fixtures cover absent/empty/malformed headers, pending unsupported commands,
unsupported optional operations and admission after an agent upgrade. No live
agent or public lab was changed for these tests.
