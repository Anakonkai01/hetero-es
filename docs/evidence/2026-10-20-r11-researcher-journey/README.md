# Researcher journey on an isolated r11 candidate2 lab (2026-10-20)

The packaged candidate2 Lab Server (`.scratch/r11-builds/lf1-20261020-r11-candidate2/`) ran as an isolated lab on the
5070 Ti (own XDG dirs, port 8790, Tailscale address), never the live lab. Driven by Playwright as a platform admin and
a newly registered researcher: register → approval → workspace creation permission → create a workspace → pair the
candidate2 Linux Worker (coordinator) → approve the device → register the pinned Qwen manifest → import GSM8K v1
(2000/500/1319, pre-split) → create a v3 experiment with non-default settings → submit → contribution ON → run.

`frictions.md` lists every finding (bugs, untranslated text, missing features); the fixed ones name their commits.
`mutation/` holds the mutation-check inputs and results of each fix (all listed mutants killed except the sampler,
whose check was not run). Screenshots and scripts stay in `.scratch/isolated-lab/journey/` (not committed).

## What this does NOT show
- No Windows, no 3060, no multi-machine run: the 3060 was offline the whole session. One GPU (5070 Ti) was coordinator
  and worker at once.
- The fixes ran in the isolated Worker only by patching its installed runtime copy in scratch; no candidate3 was built,
  and the web/backend fixes were not seen in a packaged server (the isolated server is still candidate2).
- The baseline experiment's results (rewards, hashes, timings) are not recorded here yet; nothing about learning.
- A new model (other than the shipped Qwen) cannot be qualified on devices yet; the journey used the shipped model.
- `scripts/check-all.sh` was not rerun after these commits.
