# r11 desktop-v3 worker profile generated safely — 2026-10-19 (intermediate)

Handoff `docs/handoff-v3-audit-recovery.md` section 5 step 3. Code: `3ac7b99` (fresh output directory,
explicit `--profile`/`--reference-dir`), `76cc805` (`--pinned-profile`
for report rows without a hash) and `f5c3ca0` (bounded retry of wheel size lookups).
`desktop/worker/resources/` was **not** written or edited.

## Command

```bash
python3 -I scripts/build-worker-profile.py --track-a runtime --reports .scratch/v3-r11-reports \
  --profile desktop-v3 --reference-dir .scratch/v3-reference-20261019/5070ti \
  --pinned-profile desktop/worker/resources/profile.json --out .scratch/r11-profile-f5c3ca0
```

Inputs: the actual-OS pip reports committed in `../2026-10-19-v3-windows` (byte-identical copies), the
reference of `../2026-10-19-v3-qualification-reference`, and the current reviewed r10 profile.

## Results

- `generated/`: `profile.json` (`profile: desktop-v3`), both lock files and `reference.json` (the v3
  reference, beside `reference-v3-adapter.bin` `051b79e3…` in the output). `generated-files.sha256` lists
  every output including `runtime.tar.gz` (180 KB, not committed).
- Compared with the shipped r10 profile: the only lock-file changes are the additions
  `accelerate==1.15.0`, `peft==0.21.2`, `psutil==7.2.2` on both platforms (`requirements-*.diff`); every
  existing package keeps its version and its hash; the Python archives and the seven model files are identical.
  Windows 38 wheels / 2.99 GB download, Linux 56 wheels / 3.79 GB (including Python and model).
- The PyTorch index gave no hash for `torch` and `Jinja2` in both reports. Those two rows take the hash of
  the identical URL from the reviewed r10 profile; a different URL is refused (tested).
- `r11-profile-build*.log`: the first three attempts failed on TLS handshake timeouts to
  files.pythonhosted.org during size lookups (the partial output directory was removed each time); after
  the bounded retry the fourth attempt passed. An earlier attempt failing on the missing hashes printed to
  the console only.
- Tests `profile-tests.log` (10) and mutations `mutation/`: 10 + 1 + 3 + 3 mutants, all killed after one
  added test (archive mtime).

## What this does NOT show

- Intermediate: `runtime.tar.gz` is the runtime at `f5c3ca0`, before `qualification.main`, setup and backend
  wiring (steps 4–5). The r11 profile must be regenerated from the final commit; nothing here is a release.
- No installer was built, signed, installed or published; nothing was copied into `desktop/worker/resources/`.
- Sizes come from range requests, hashes from pip reports (or the reviewed profile); no wheel was downloaded
  and re-hashed here.
- Native Windows C: had about 3.5 GB free; a 2.99 GB download plus installation will not fit there.
