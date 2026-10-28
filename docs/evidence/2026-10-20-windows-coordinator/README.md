# Real native Windows coordinator, Quang WSL worker (2026-10-20)

A short system parity run uses pinned Qwen2.5-0.5B-Instruct, FP32 HF greedy evaluation, full weights, canonical CPU noise,
antithetic population 4, two generations, sigma 0.025, alpha 0.005, four training prompts per candidate and eight new tokens.
`reward.py.txt` scores distinct output characters; this is a mechanics reward, not a learning experiment. Candidate seed
namespace is `session4-windows-coordinator`. `rows.json` is the entire synthetic dataset.

The reference is a 5070 Ti coordinator + local GPU worker (`heteroes run`); the distributed case is a **native Windows**
RTX 3060 coordinator on Thao's machine (`heteroes serve`) with Quang's RTX 3060 WSL worker (`heteroes worker`). The Windows
runtime reports its native OS in `windows-environment.json`. All Torch/Transformers/NumPy versions match the pinned stack.
The isolated lab's contributions were turned OFF before these independent checks; the public lab was not changed.

`comparison.json`, exported by `compare_receipts.py`, compares both generation record hashes, all eight candidates' texts and
rewards (32 texts), and both child weight hashes. They are identical. Both updates are non-noops (over 493 million
FP16 elements changed in each). Child hashes are `5e1cc555…` then `88733e3f…`. The remote worker replayed the update with
verification and exited `finished`. Raw ledgers and token files remain private in scratch; only numerical receipts are
committed. `source-files.json` records every Python source file transferred to the native runtime, including staged CLI code.

## What this does NOT show

- Audits are disabled in this two-device case: there is only one candidate-generating worker. The independent exact
  comparison covers every candidate; distributed audit mechanics are tested with two CPU worker processes separately.
- This is not a managed web-lab Windows coordinator run, an installed candidate3 acceptance or Windows CPU acceptance.
- No speedup is claimed. Generation 0's waiting time includes manually starting the remote worker; the stored timers are
  not a fair one-vs-two-machine benchmark. This tiny run establishes no learning benefit or generalization claim.
- No push, tag, deployment, live device approval or public installer publication.
