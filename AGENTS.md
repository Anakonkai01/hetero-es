# AGENTS.md — HeteroES

One repository: numerical runtime in `runtime/`; CPU product, web/apps and operations at the root. Both original histories
and `archive/runtime/*` / `archive/product/*` branches are retained. Read `docs/HANDOFF.md` first, then the relevant module
and `runtime/docs/numerical-contract.md` for numerical work. Historical agent/session files under `docs/archive/` are dated
records; this file contains the current common rules.

## Project claim (owner, 2026-10-20)

HeteroES contributes no new ES algorithm, and it does not set out to prove that ES learns; published papers already
show that. Its contribution is the system: ES post-training on heterogeneous consumer GPUs that is correct, reproducible
and measurable, offered to researchers as a lab they can sign up to and customize. Do not spend GPU-days on learning
runs to "show ES learns". A learning run is at most a later, cheap parity check against reference code, and only when
the owner asks. Prefer finishing the system (product, multi-machine, speed, researcher features) over writing reports.

## Working rules

- Talk to the owner in Vietnamese, simply and briefly. Code comments and general documentation are English; the approved
  Vietnamese quickstart/plan keep their language.
- Complete authorized work autonomously. Commit logical groups on a working branch. Push and merge are authorized by the owner (2026-10-20):
  `origin` is `git@github.com:Anakonkai01/hetero-es.git`; `git push origin --all` is allowed, merges into `main` are
  fast-forward only. Never force-push, never delete remote branches, never push tags; if a push is rejected, stop and
  ask. Never add `Co-Authored-By`, generated-by or session trailers.
- Write meaningful tests before new behavior/helpers; use `scripts/mutation-check.py` on scratch copies. A surviving
  mutant needs a test or a documented equivalence. Preserve intermediate receipts and state their limits.
- Never print or commit passwords, credentials, device/session tokens, signing keys or tunnel secrets.
- Existing evidence and `runtime/artifacts/` are immutable. Add a fresh dated evidence folder with a README containing
  **What this does NOT show**. Do not format fixtures, resource profiles, generated files or archives.
- Do not change device approval/contribution based on an old handoff. `3060-thao` is REVOKED in the latest live read.

## Lab and hardware

The live/public lab runs from `~/.local/share/heteroes-lab/app` at its deployed commit, with its own environment. The
working tree and local `main` can advance without deploying it. Change lab state only through `scripts/local-lab.py`.
Do not restart its unit directly, kill processes manually, use `pkill -f`, or start another controller against its database.
No cleanup installer is published; installer polish/r11 is separate. Keep the existing Conda `ai` environment unchanged.
SSH to another machine requires a specific owner request; historical SSH permission does not authorize new remote work.

GPU computation requires the owner's authorization, an explicit `--gpu` where supported and
`HETEROES_GPU_ACCEPTANCE=1`. CPU checks use `CUDA_VISIBLE_DEVICES=''`. Never use `/mnt/sekai`. Verify the selected Archive
disk UUID before writing there. Private state/runtimes stay on the system filesystem; packaging checks use `.scratch/`.

## Numerical contract

Recipe v1 behavior is frozen. `runtime/src/heteroes/{noise,es,ledger}/` and `generation_record.py` may only be formatted
with strict Python AST-equality proof unless the owner separately approves a behavior change. Follow the complete contract
and ADR-001/002, plus the decided items in ADR-004–007; do not reopen the cleanup decisions in the handoff.

Canonical CPU noise identity excludes worker/attempt/lease metadata. Perturbation uses separate FP32 multiply/add with
FP16 publication; update accumulation is FP32 in canonical candidate order. Restore is exact, a mismatch quarantines the
worker, and infrastructure failure is never coerced to reward zero. Retry/replay identity and numerical serialization
must remain unchanged. Experimental scripts and claims have their own recorded evidence; do not claim GPU/Windows or
learning acceptance from CPU or fixture checks.

## Verification

```bash
scripts/check-all.sh docs/evidence/YYYY-MM-DD-name/checks
CUDA_VISIBLE_DEVICES='' .venv-backend/bin/python -m pytest backend/tests -q
(cd runtime && CUDA_VISIBLE_DEVICES='' PYTHONPATH=src "$HOME/miniforge3/envs/heteroes-match/bin/python" -m pytest -q)
scripts/build-apps.sh --check .scratch/fresh-linux-check
python3 -I "$HOME/.local/share/heteroes-lab/app/scripts/local-lab.py" status
```

The full check includes lint/format, i18n, source-package imports, web/desktop units and fixture browser/Electron checks.
Ruff uses 120 columns; Prettier is pinned at the root. `scripts/check-python-ast.py --base <commit> --out <receipt.json>`
proves a format-only Python change; the formatting commit is in `.git-blame-ignore-revs`. Local formatter guards preserve
literal docstring whitespace. Clear `ELECTRON_RUN_AS_NODE` for ordinary Electron probes; the packaging checker sets it
only for deliberate Node-mode module import checks.
