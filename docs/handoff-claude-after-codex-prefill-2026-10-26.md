# Handoff to Claude after Codex prefill attention — 2026-10-26

The owner requested closure/handoff at about **22:14 +07**, because Codex usage was running low. No new experiment
was started after that request. Continue from the state below; do not repeat a running native job.

## Repository and selected change

- Worktree `/home/pc5070ti/projects/heteroes-codex-frozen-perf`, branch `work/codex-frozen-perf-2026-10-25`.
- Read `AGENTS.md`, `docs/HANDOFF.md`, the numerical contract and the previous
  [Claude fused-finish handoff](handoff-codex-after-claude-fused-2026-10-26.md).
- Runtime commit **`2eb4da0d`**: query/head tiles sharing K/V in short packed prefill, unchanged B22 arithmetic.
  New source/planner `runtime/src/heteroes/eval/strict_prefill_cuda.py`; dispatch/layout integration in `strict_cuda.py`.
- Test-only commit **`6cc69d26`**: ensure the mutation suite tests the actual selected default route.
  Runtime source is identical to `2eb4da0d`. The final handoff commit adds only evidence/docs.
- [Evidence](evidence/2026-10-26-strict-prefill-attention/README.md) is sealed. Existing evidence remains immutable.
- No push/merge/deploy, live lab/device-state change, learning run or `ai` environment change. Original worktrees untouched.
- The owner explicitly authorized SSH to 3060-thao for **both WSL2 and native Windows** during this session.

## Result, with the correct paired baseline

5070 Ti, separate-process ABAB with an idle host:

| Case         | `48547ba3` | `2eb4da0d` |   Gain |
| ------------ | ---------: | ---------: | -----: |
| Qwen short32 |     8746.3 |     8922.1 | +2.01% |
| Qwen chat128 |     8865.7 |     9108.7 | +2.74% |
| Smol short32 |     8372.1 |     8526.7 | +1.85% |
| Tiny short32 |     4534.6 |     4644.3 | +2.42% |

3060 WSL2: Qwen **+2.01% / +2.07%**, Smol **+4.50%**, Tiny **+1.76%**. All token hashes match.
Do not attribute the entire difference from the old CPU-contended 8580 to this change.
Qwen short32 is still only **64.5% of vLLM 13835**. The goal is not achieved; M0–M6 remains after performance work.

Prefill chat CUPTI: attention **25.29 → 12.26 ms**, whole prefill **118.7 → 106.8 ms**. Projections remain **71 ms**.
The new kernel uses one warp per query/head slot, aligned pruned trees, bounded shared memory and call-local
metadata. Decode layouts and ineligible shapes keep the old GQA/split path. Portable identity includes the new module.

## Completed gates

- 5070 Ti targeted GPU **458 passed**; six-architecture PTX/SASS audits (SM75/80/86/89/90/120).
- WSL2 **1002 passed**, exit 0 (`tests-3060-repaired-02.log`). The test-only default-route fix is included.
- All three trained models: parent, canonical seed7001 ±sigma, restore; Qwen chat128 and real EOS:
  both GPUs match each other **and the sealed fused-finish receipt**, including prefill logits and weights.
- Mutation: 10/11 initially, one actual fixture gap fixed and killed in the 1/1 rerun; no surviving new mutation.
- `check-all`: **ALL PASS**, runtime CPU **3237/884 skip**, backend **452** plus web/desktop/browser/Electron checks.
- Linux source-copy packaging passed; all **142 runtime Python files** in the Worker archive match the checkout.
  The 910 MiB packaging scratch tree was removed after preserving receipts/hashes.

## First action: observe the existing native Windows job

**Windows is still running. Its result is not accepted yet. No local GPU experiment is running.**

At closure the native controller is local Linux PID **2467350**, with SSH child **2467662**; the Codex tool session
was `57703` (Claude should use OS processes/files, not assume that tool handle transfers). These can exit after
completion or if the Codex application is closed; inspect the Windows process/report before restarting anything.
The read-only native process snapshot is `evidence/2026-10-26-strict-prefill-attention/raw/3060-native-01/processes-at-close.json`.
That snapshot identifies Windows Python launcher PID **18632** and interpreter PID **23336** (parent PowerShell 6400).

Live local console (outside sealed evidence):

```bash
tail -30 .scratch/codex-prefill-20261026/native-live-console-01.log
ps -p 2467350,2467662 -o pid,ppid,etime,comm
```

SSH: `ssh -F /home/pc5070ti/.ssh/config -o BatchMode=yes -o ConnectTimeout=8 thao_nguyen@100.92.20.58`.
Native Windows cache (also visible through WSL):

```text
C:\Users\Thao Nguyen\.cache\heteroes-native-strict-20261025-01\
/mnt/c/Users/Thao Nguyen/.cache/heteroes-native-strict-20261025-01/
```

Exact files/directories:

- Archive `source-codex-prefill-01.tar.gz`, SHA256 **`bfaf5e6cb058b1a20085e79ca373fcaf3cabe955c8675cc17b60b6c2bea1eeb2`**.
- Extracted source `stage-codex-prefill-01/`, new COMMIT `6cc69d26` (runtime `2eb4da0d`), base `48547ba3`.
- Output `codex-prefill-01/`: `qwen-parity-native-01.json` and four `single-qwen-*-native-*.json` once produced.
- Final runner receipt **`codex-prefill-native-run-01.json`** in the cache root. Written at completion, success or error.
  Require `status=ok`, `pytestExitCode=0`, trained parity exit 0, all four benchmark exits 0, both manifest checks true.

The native suites include the new prefill tests and the earlier fused-finish/decode changes whose native gate was
still open in Claude's handoff. They are substantial (the previous native suite took about 14 minutes).
After units, current Qwen parent/±/restore and captured real-EOS are run, then ABAB timing.

**Native EOS protocol:** it reuses the sealed full uncaptured oracle after strict experiment/state/input/EOS
identity checks, rather than repeating a 17–18 minute uncaptured generation. The current captured 32-row EOS
generation is executed and compared exactly. The new receipt explicitly records
`uncapturedEosControl.measuredInThisRun=false`; do not claim the old oracle was rerun on current native source.
The helper has 15 tests, 7/7 killed mutations and a successful local integration (32 s). The control archive is
manifest-covered. Current native uncaptured APIs are also exercised by the ordinary decoder/unit suite.

If the job is alive, poll its existing console/report; do not launch another job on the 3060. If it disappeared,
first inspect the final runner receipt and process list. A missing observation is not proof the job stopped.
If a real interruption requires a new run, retain partial output and use fresh `-02` archive/stage/output names.

## Collect native results without changing sealed evidence

Create a fresh folder such as `docs/evidence/2026-10-26-strict-prefill-native-finish/raw/` and collect the final
runner receipt plus the contents of `codex-prefill-01/` there. Copy the live console only once it has finished.
Then run the sealed comparer, directing its output to the new folder:

```bash
python3 docs/evidence/2026-10-26-strict-prefill-attention/summarize.py \
  --native-dir docs/evidence/2026-10-26-strict-prefill-native-finish/raw \
  --out docs/evidence/2026-10-26-strict-prefill-native-finish/summary.json
```

It requires all native runs and compares native Qwen with both Linux hosts and the sealed B22 receipts. Without
native, `summary-5070-wsl2.json` is explicitly marked pending. Update HANDOFF only from actual results, then seal
the new follow-up folder. Do not overwrite this checkpoint's manifests, snapshots, README or partial summary.

WSL completed stage: `/tmp/heteroes-codex-prefill-20261026-02`, all parity/timing and repaired test logs are copied
locally. A reboot erased the first stage. Isolated pytest then needed the `py.py` shim in
`/tmp/heteroes-codex-prefill-pytest-shim-02`; no remote Python environment was changed. The initial import failure
is preserved separately from the successful 1002-test rerun. WSL/Windows share one physical GPU.

## Rejected pilots and next work

The frozen experiment sources/receipts are under the evidence `harness/experiments/` and `raw/`:

1. Prefill projection 64x32 tile: eight local bit/oracle tests pass; unchanged to **5% slower** on five shapes.
2. 64x64 with 60 KiB dynamic shared memory: eight local tests pass; **18–42% slower**. Operator-only code;
   do not install that prototype into a decoder because other stream launches do not supply its dynamic memory.
3. GQA denominator warp trees + eight-slot value counter: **53 local tests**, only **0.6–2.7% operator gain**,
   registers remain 82. No end-to-end, mutation, architecture or remote gate; not selected.

Continue from the measured bottlenecks. Prefill projections dominate the remaining 107 ms; simply enlarging
the row tile has now been measured and rejected. Attention decode's value phase still grows with context
(about 31 us/layer at 270 keys, 54 us at 512 in the finite operator probe); removing denominator barriers alone
does little. Decode projection wave balance remains open. Do not repeat the earlier discarded PDL/L2-prefetch/
cluster/SiLU experiments without new evidence. Do not substitute wrapper/vLLM speed or duplicate-prompt tricks
for the owner's strict-kernel objective. Preserve D1–D11 and the complete M0–M6 plan.
