# New-model qualification on real GPUs (2026-10-20)

Packaged build `lf1-20261020-sysfinish-q1` from `2965485` (Server, Worker app and the Linux CLI bundle on the Archive
disk), on the isolated lab (`100.110.165.40:8790`), upgraded in place with its existing data.

Two models that are not the shipped Qwen2.5-0.5B were made into pinned manifests with `heteroes manifest` (only the
config, tokenizer and safetensors files; SmolLM2's pickled `training_args.bin` and ONNX files were left out), registered
as recipe v3 uploads by the researcher account, uploaded and published (`*.manifest.json`):

| Model | Manifest hash | Lab reference | 5070 Ti (packaged Worker app, Linux) | 3060 Quang (`heteroes-worker` CLI, WSL2) |
| --- | --- | --- | --- | --- |
| Qwen/Qwen3-0.6B `c1899de2…` | `b07731af…` | `33d29f74…` | BUILD_REFERENCE COMPLETED | COMPARE_REFERENCE COMPLETED |
| HuggingFaceTB/SmolLM2-360M-Instruct `a10cc151…` | `9daf23fa…` | `b3ee96d5…` | BUILD_REFERENCE COMPLETED | COMPARE_REFERENCE COMPLETED |

COMPARE_REFERENCE COMPLETED means the lab re-checked the 3060's signed repeats, outputs, rewards and exact restore
against the frozen 5070 Ti reference and accepted them (`qualification-jobs.txt`). `devices.json`: both devices run the
pinned Python 3.12.15, torch 2.13.0+cu132, transformers 5.17.0. The 3060 was set up only with the one-line installer
(`quang-install.log`: pinned Python, wheels and model downloaded and SHA-256 checked), then `heteroes-worker selftest`
(passed in 28 s), `join` with a pairing code made by the researcher, admin approval, `run`, and ON from the lab.

A first Qwen3 request to the 3060 was refused before contribution reached the device; the retry is the recorded job.

## What this does NOT show

- The third machine (3060 Thao) is missing: its WSL SSH server closed every connection during the session.
- Native Windows was not used; the 3060 ran in WSL2 with the Windows driver.
- Qualification checks a fixed probe (signed repeats, texts, rewards, restore); it does not certify every workload,
  decoding setting, near tie or learning benefit, and no training run was made with the new models.
- The installer was not served from a lab download page; the bundle was copied over SSH and given as HETEROES_BUNDLE.
