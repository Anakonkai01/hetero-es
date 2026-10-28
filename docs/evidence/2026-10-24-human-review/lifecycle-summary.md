# First single-model CPU lifecycle probe

Probe: `runtime/scripts/profile_single_model.py`, pinned Qwen2.5-0.5B revision
`7ae557604adf67be50417f59c2c2f167def9a775`, CPU, two torch threads, seed 7001,
one candidate, sigma 0.001, four new tokens. Native HF FP16 inference; no shadow evaluator.

- Live unique parameter/buffer storage: 988,065,792 bytes (parameters are 988,065,536 bytes).
- CPU snapshot: 988,065,536 bytes.
- Whole process peak RSS: 2,928,791,552 bytes. This includes framework/loader/temporary memory.
- Exact restore passed and parent SHA-256 before/after matched.
- Full phase samples: `qwen-cpu-single-model-01.json`; command output: matching `.log`.
- `lifecycle-probe-mutation-01.log`: five control tests passed; all four targeted guard/restore mutants killed.
- Intermediate failures: `lifecycle-probe-red-01.json` and `lifecycle-probe-red-02.json`.

## What this does NOT show

This is one resource/correctness probe, not a speed distribution, quality/learning evaluation, cross-GPU token
equality test, GPU peak measurement or native Windows acceptance. Four generated tokens truncate the response;
the recorded reward is not a model-quality conclusion. The strict operation reference remains separate experimental work.

