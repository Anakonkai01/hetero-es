# Separate CPU-guard decoder implemented and checked

Source commit **f5d311b** adds opt-in Recipe v3 `hf_fp32_cpu_guard_v1`; owner approval is recorded in
`docs/plan-r11-release.md`. Primary generation remains FP32. Near-tied unfinished rows use a lazily
created CPU FP64 reference of current candidate weights; failure is an error, never an unchecked token
or reward zero. No frozen noise/update/ledger source or historical recipe meaning changed.

The v3 configuration, supervisor, templates, checkpoint evaluation and experiment wizard admit the new
identity. Recipe v1 retains its original vocabulary. FP16, builtin workloads, sampling and unsupported
generation modes/processors are refused. CPU copies preserve tied parameters, check available RAM and
the 8 GiB reference limit, and use a weak forward-method reference to avoid a multi-GB ownership cycle.

## Verification

- **23/23 combined checks ALL PASS** on the final stable source: `final-checks/`; **2,504 runtime passed,
  102 skipped**, **375 backend passed**. CPU only; browser/Electron fixtures, type/lint/format/i18n,
  source archive imports included. `checks/` is an earlier passing run started before the lifetime
  regression was added; it is retained but superseded by `final-checks/` for final-source acceptance.
- **19 focused CPU tests** cover row/prefix selection, EOS rows, repetition/left padding, no unnecessary
  CPU allocation, memory refusal, scoped precision, tied/current weights, immediate reference release,
  failed-candidate restore/no completions, identity/admission and unsupported modes. Tests-first failures
  are retained. All **12 scratch mutations killed**, including restoration of the ownership cycle.
- Managed coordinator/worker CLI tests pass for full/subset/LoRA with the new decoder. These are CPU
  fixtures, not native Windows or real-model cross-OS LoRA evidence.
- Final-source hardware probe: all **8 original generation-10 candidate indices/seeds/signs**, followed
  by c5 again, on **5070 Ti and Quang WSL RTX 3060**. All **9 full token arrays, decoded texts, input
  masks/IDs, perturbed FP16 and primary FP32 weight hashes agree** across both devices. Every parent
  restores exactly. Both c5 evaluations match the original 5070 completion hash `519e5172210e...`.
- New recipe hash `11136dc840e494f27fdfa5930f9b84ec73bb184dcdbee9b2062ef0e0adb617dc`; original
  `859658c6316aba7caf79e1144ec239fe8af0d4991ea7be6ff63dd221ac35863d` remains untouched. Final decoder
  source SHA256 `150ac9fdd1464e6cdb41bbc624173de28f01f53019a04f18b77e178ceb2ea95d` matches both probes.
- CPU reference call counts on both machines: **0, 2, 0, 4, 1, 2, 3, 0, 2** (14 total/device). No reference
  was allocated for the three zero-call cases. Reference size including buffers: **3,952,262,656 bytes**.
  GPU peak allocation reported across candidates: **2.877 GiB** on 5070 / **2.854 GiB** on Quang; primary
  parameters are asserted FP32 on GPU before/after every generation. CPU reference parameters are CPU FP64.
- Available CPU RAM after candidates: 5070 **24.096 → 23.220 GiB**, Quang **11.606 → 11.047 GiB**;
  this is host availability, not an isolated RSS/leak benchmark. Immediate ownership release has its own
  regression. The nine-case test does not establish a long-duration memory bound.

## Operator/implementation corrections preserved

The first scratch mutation control failed because HF 5.17 represents unset beam/return counts as
`None`, meaning default one. Validation was corrected to accept None/one and reject actual multiple
beams/returns; all mode controls then pass. A later lifetime test exposed the strong bound-method cycle;
the weak method fix and 12-mutant control precede final combined/hardware checks. Initial two-repeat
GPU receipts are supplementary; `*-final.json` is the final-source expanded proof.

## What this does NOT show

The empirical 0.01 gate is not a numerical error bound; CPU FP64 is finite precision too. These checks
do not establish universal bitwise inference, large-model cost or Windows GPU acceptance. The historical
parent was independently reconstructed and verified; this is not a newly evolved generation or a managed
run. No 50-generation acceptance, planned outage/retry or full independent run parity has happened yet.
Candidate6 packaging and renewed installed-device checks follow. No public publication or live deployment.
