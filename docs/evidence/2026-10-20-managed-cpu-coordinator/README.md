# Managed CPU coordinator + Windows GPU worker through `serve --lab` (2026-10-20, r11 candidate4)

Real managed run in the isolated lab (candidate4 Lab Server on this machine, workspace bcbece5a…). Coordinator: a
fresh headless Linux CLI installed in **Thao's WSL** with the one-line command
`curl -fsSL http://<private>/install-worker.sh | HETEROES_DOWNLOADS=http://<private> bash`, CPU self-test
`coordinator-cpu-v3`, offered by `heteroes serve spec.json --lab … --device cpu`. Worker: the **native Windows RTX 3060**
desktop Worker upgraded in place to candidate4 (silent installer, hash checked; pairing and D: model cache kept), GPU
self-test passed and qualified for the pinned model. The CLI paired itself, waited for administrator approval, reused
the already registered model (same manifest hash), uploaded the dataset, froze the Python reward and submitted;
approval and contribution ON were done separately in the lab, as designed.

Run `d54574d3…`: Qwen2.5-0.5B-Instruct FP32, canonical CPU noise, full weights, antithetic population 4, 2 generations,
8 new tokens, Python reward `distinct-characters` (`reward.py`, `rows.json`, `spec-thao.json`, `documents.json`).
It COMPLETED; children `6e310af6…` then `dfbc8961…`; `thao-offer.txt` is the nonsecret offer receipt.

**Parity** (`parity.json`, tool `verify_managed_run.py`): the run's own recipe/plan/dataset and ledger copy were fetched;
on the local 5070 Ti every candidate was re-executed (context computed locally), rewards recomputed with an independent
copy of the reward function, and each recorded update applied here. All 32 texts (and their completion hashes), all 8
rewards, both records' rewards and both child weight hashes are exactly equal. So the Windows 3060 texts and the CPU
coordinator's FP16 updates equal a CUDA re-execution bit for bit. `parity-first-compare-bug.json` is the first
attempt, whose text comparison was wrong (it compared the ledger's `(sha, texts)` pair with a list); rewards/children
were already equal there.

**Usage** (`usage.json`, lab API and `experiment-detail.png`): 256 generated tokens (8 candidates × 4 rows × 8 tokens,
no EOS), 10.515 reported GPU seconds from the Windows worker, 0 coordinator GPU seconds (CPU), coverage complete. The
browser view shows completion, rewards, candidates, checkpoint and the usage facts without page errors.

## Bugs found on the way (fixed before this run)

- Candidate3 coordinator agent refused every managed Python reward (`2026-10-20-managed-python-coordinator`).
- A run cancelled before its coordinator accepted it was never released (`2026-10-20-cancel-before-coordinate`).

## Quang

The first attempt used Quang's WSL as CPU coordinator (`quang-cli-install-candidate3.log`: one-line install OK in 66 s).
While upgrading it to candidate4, Quang's WSL began returning I/O errors (`quang-cli-upgrade-candidate4-io-error.log`)
and SSH then reset; most likely the Windows C: drive holding the WSL virtual disk ran out of space (owner's assessment;
not verified, the machine was unreachable). Thao's C: was checked before and after (26 → 21.6 GB free).
The cancelled candidate3 experiment `ec1c8f27…` still holds the 5070 Ti and Quang's CLI device: the lab correctly
waits for that device to confirm its processes stopped. It will release once Quang's agent reports again.

## What this does NOT show

- Audits are off (one generating worker). No speedup, learning or generalization claim; 2 tiny generations only.
- Not a Windows CPU coordinator run, not a Linux packaged desktop GPU worker run in this configuration, not public.
- Windows uninstall/restart of candidate4 is not covered here. Nothing was pushed, tagged, published or deployed.
