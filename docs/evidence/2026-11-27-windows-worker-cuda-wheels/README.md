# 2026-11-27 — Windows Worker profile with the CUDA wheels of the strict decoder

Before commit `fdf359a3` the Windows Worker profile (`desktop/worker/resources/profile.json`, `requirements-windows.txt`)
had no `cuda-bindings`/NVRTC, so the packaged Windows app could not run `strict_b22_v1` (`No module named 'cuda'`).
The earlier native-Windows acceptance pairs never saw this: they run in a hand-built venv through
`acceptance/native_python.py`, not in the app's pinned environment.

`fdf359a3` adds `cuda-bindings==13.4.3`, `cuda-pathfinder==1.8.3`, `nvidia-cuda-nvrtc==13.2.78` and
`nvidia-cuda-nvdisasm==13.2.78` (Windows wheels, same versions as Linux) and makes the agent bridge and the self-test put
`<python>\Lib\site-packages\nvidia\cu13\bin` first on `Path` (`desktop/worker/electron/agent-env.cjs`). `runtime/` is
unchanged; the packaged runtime is still `01446be01907`. Installer build `20261127-fdf359a3`
(`/mnt/Archive-2tb/HETEROES-LAB-KHONG-XOA/builds/20261127-fdf359a3`).

## Check on native Windows (`3060-quang`, RTX 3060, Windows 11 26200, driver 617.42)

`check-packaged-env.ps1` repeats what `setup.cjs` does, from the resources inside the built installer
(`win-unpacked/resources/worker`): the pinned Python 3.12.15 archive and every Windows wheel downloaded and checked
against the profile's SHA-256, `pip install --no-index --require-hashes -r requirements-windows.txt`, `runtime.tar.gz`
checked against `runtimeSha256` and extracted. It then sets the app's environment (agent-env: Path, `PYTHONNOUSERSITE`,
`PYTHONUTF8`, `PYTHONPATH` = packaged `src`) and runs `acceptance/probes/strict_parity.py --gpu --model qwen`
**without** `native_python.py`. The Qwen model is the Worker's own pinned snapshot (`7ae55760…`, same SHA-256 as the
acceptance copy).

- `check-1-missing-probe-module.log`: first attempt. All 42 wheels installed, `cuda.bindings 13.4.3` imported and
  `nvdisasm.exe` found through `Path`; the probe then stopped because `runtime/scripts` (its helper module) had not been
  copied to the machine.
- `check.log`, `parity-qwen.json`: second attempt with `runtime/scripts` copied: `status ok`, no mismatches, 72.6 s,
  `PARITY OK`. Cases, EOS result, golden hash and `kernelIdentity.fingerprint` (`24f6e3eb…`) are identical to the
  native-Windows acceptance receipt of 2026-11-26 on the other RTX 3060 (`strict-parity-qwen-native`, source
  `src-3fce794a`).

The folder on the borrowed machine (6.1 GB on D:) was deleted afterwards.

## What this does NOT show

- The NSIS installer itself and the Electron app were not run on Windows; only the environment they create was rebuilt
  by a script. Onboarding, device approval and a lab run from the Windows app are not checked.
- Only the Qwen parity probe ran. The native GPU test suite (`strict-gpu-suite-native`) and `noise-es-gpu-native` were
  not run in this environment; the probe's receipt has no per-kernel SASS audit record (`builds` is empty), so it shows
  that `nvdisasm.exe` is found, not that every audit ran.
- One machine, one GPU model (SM86). No speed, memory or long-run claim.
