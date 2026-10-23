# 2026-10-22 ~19:00: candidate13 (real-user fixes) deployed and accepted; session closed

Branch **`feat/real-user-c13`** (not pushed). Lab on **`948059b`** (build `lf1-20261022-r11-candidate13`); agents
5070ti-nhan and 5070ti-nhut on **`lf1-20261022-r11-candidate13b`** (runtime `756272d28ef3`, finding 12 fix); the
candidate13b installers are published. Lab idle. Evidence: [evidence/2026-10-22-candidate13/](../../evidence/2026-10-22-candidate13/README.md).

## Done this session (owner's scope from the grill, memory `hetero-es-real-user-c13-2026-10-22`)

- Tier 3 parity ALL EQUAL (71 child hashes, generations 0 and 70 regenerated); RESULTS.md tier 3 closed.
- Findings 9 (re-add = `worker_joined` rejoin), 10 (deployed), 11 (`worker_unreachable`/`worker_reachable`, lost on the
  live view), 12 (public dataset download needs the worker User-Agent; found by the acceptance).
- Devices: rename and one-step delete (revoke + remove) for the owner and the administrator.
- No Tailscale by default: public dataset upload (≤ 64 MiB, own Caddy limit), `doctor`/`setup` wording; a fresh
  install of 5070ti-nhut with its tailnet blocked paired, updated and worked over the public address only.
- Notebook → lab: `heteroes.sdk_lab` (Lab/Model/Dataset/Run, hub REFERENCE models, own loader, cell-written reward and
  sampler, qualification before the experiment, `suggest` for batch/chunks), Python sampler `python@1:<sha>`,
  per-GPU chunk memory measured at model qualification, notebook `runtime/notebooks/researcher.ipynb`, create page
  leads with the notebook; the lab serves the notebook and the SDK wheel at `/notebooks/`.
- Acceptance run from the notebook: `fde1fccf…` COMPLETED, parity ALL EQUAL.
- Chunk 128 probe: texts equal on 5070 Ti and 3060 at 16/64/128, but only ~5 % faster than 64: **not enabled**.

## Next session (in order)

1. **Owner tries the web** (acceptance item 3): rename a device; Delete the two revoked ones (old `5070ti`,
   old `5070ti-nhut` `cli-aa99b4d4ca58`); the create page and `/notebooks/` links; the live view of `fde1fccf`.
2. **Lab redeploy to `f29e9c4`+** only for the web/notebook changes after `948059b` (notebook `suggest(devices=…)`),
   by the owner (`deploy-lab-c13.sh` pattern with the 13b build; the classifier refuses stopping the lab).
3. **Windows app on 3060-thao** (someone at the screen): the candidate13b Windows installer; then the 3060 in a
   notebook run, which also exercises a real model qualification and the chunk measurement (never run on a GPU yet).
4. Open, smaller: ~~`/api/v1/workers` lists revoked devices~~ (fixed in the SDK, `f30aa06`, ships with the next notebook/wheel redeploy; the web list still shows them on purpose so they can be deleted); an audit was not
   drawn in the acceptance run (5 % of 40): a run with audits on this build; the 1660S is offline (hardware).
5. Decide with the owner: chunk 128 (5 % gain), push/merge of `feat/real-user-c13`.

## State to know

- 5070ti-nhut: an iptables rule rejects NEW outbound connections of user `heheboiz` to 100.64.0.0/10 (the
  "no Tailscale" acceptance). Not persistent across reboots; remove with
  `sudo iptables -D OUTPUT -d 100.64.0.0/10 -m owner --uid-owner 1000 -m conntrack --ctstate NEW -j REJECT`.
- The lab session token in `~/.config/heteroes-demo/session.json` expires ~06:00 on 10-23.
- Researcher venv for checks: `.scratch/c13-researcher` (SDK installed from the lab's wheel).
- Rules learned again this session: `runtime/src/heteroes/{noise,es,ledger}` and existing evidence are not edited
  (a ledger getter was reverted, `052d87e`); no `Co-Authored-By` trailers.

## Update ~19:40 (same day): lab-only update `2047452` + audit run, FINDING 13 open

- Lab redeployed by the owner to **`2047452`** (`evidence/2026-10-22-candidate13/deploy-lab-c13c.sh`, rollback
  `deploy-lab-rollback-c13c.sh`; agents stay on 13b). Live view now shows device names (`89710ff`), the notebook's
  device table leaves out revoked devices (`f30aa06`). The owner deleted the revoked devices on the web.
- Audit run `4eadb5b4…` from the notebook ([evidence/2026-10-22-candidate13c-audit-run/](../../evidence/2026-10-22-candidate13c-audit-run/README.md)):
  10/10 generations, audits 9 selected / 8 completed / all matched (done: next-session item 4 of the list above).
- **Finding 13 (do first next session, Opus, effort high):** nhut's worker (`cli-34312a79fbbc`) died after generation 7;
  its replay of the 8th update (g7→g8) gives `2b9b3f1e…`, expected `d864a9b6…`, identical on all 6 automatic restarts.
  Unknown whether the coordinator's chain or nhut's replay is wrong. Start with a ledger replay of the child hashes
  (`verify_managed_run.py … --regenerate none`, run dir from `~/.config/heteroes-m2/state`), then the same update on
  the 5070 Ti vs nhut's machine. Also ask whether 6 identical restarts of a deterministic failure should be capped sooner.
- The audit rate cannot be set from the notebook (fixed 0.05 on the lab path); more candidates = more audits.
- The lab session token in `~/.config/heteroes-demo/session.json` was used by the run (expires ~06:00 10-23).
