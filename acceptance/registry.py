"""
Every acceptance check and every gate of milestones M0-M6 (docs/PLAN-SUA-HUMAN-REVIEW.md, section 7; on the branch
evidence-archive).

Change a gate from `open=` to `checks=` only together with the tests or probes that prove it. A `deferred=` gate needs
the owner's decision or a hardware limit stated in its reason; it is printed in every report.
"""

from acceptance.core import Check, Gate

GPU = (("HETEROES_GPU_ACCEPTANCE", "1"),)
RUNTIME_PATH = (("PYTHONPATH", "src{extra}"),)
PROBE_PATH = (("PYTHONPATH", "{repo}/runtime/src{sep}{repo}/runtime/scripts{extra}"),)
LINUX_GPU = ("local", "3060-wsl")

# Native Windows: the modules that run there (SASS audits need the native nvdisasm; see acceptance/native_python.py).
NATIVE_TESTS = tuple(
    f"tests/eval/{name}.py"
    for name in (
        "test_integer_lm_head",
        "test_integer_weights_batched",
        "test_integer_balanced_plan",
        "test_integer_nonpower_split",
        "test_strict_graph_host",
        "test_integer_stream",
        "test_strict_decode_pipeline",
        "test_integer_decoder",
        "test_integer_group",
        "test_integer_packed_input",
        "test_integer_cuda",
        "test_strict_decode_graph",
        "test_strict_cuda",
        "test_strict_packed",
        "test_strict_attention_split",
        "test_strict_attention_prefill",
        "test_integer_fused_finish",
        "test_fp16_decoder_cuda",
        "test_qwen2_strict_cuda",
        "test_integer_tma",
        "test_attention_key_stages",
        "test_request_context",
    )
) + ("tests/v3/test_v3_strict_decoder.py",)

PYTEST = ("-m", "pytest", "-q", "-p", "no:cacheprovider")

CHECKS = [
    # cpu
    Check("acceptance-selftest", "cpu", ("{python}", *PYTEST, "acceptance/tests"), timeout=600),
    Check("check-all", "cpu", ("scripts/check-all.sh", "{out}/checks"), expect="ALL PASS", timeout=4 * 3600),
    # gpu
    Check(
        "strict-gpu-suite",
        "gpu",
        ("{runtime_python}", *PYTEST, "tests/eval", "tests/v3/test_v3_strict_decoder.py"),
        hosts=LINUX_GPU,
        env=GPU + RUNTIME_PATH,
        cwd="runtime",
        timeout=3 * 3600,
        gpu=True,
    ),
    Check(
        "strict-gpu-suite-native",
        "gpu",
        ("{runtime_python}", "{repo}/acceptance/native_python.py", *PYTEST, *NATIVE_TESTS),
        hosts=("3060-native",),
        env=GPU + (("PYTHONPATH", "src{sep}tests/eval"),),
        cwd="runtime",
        timeout=3 * 3600,
        gpu=True,
    ),
    *[
        Check(
            f"strict-parity-{model}",
            "gpu",
            (
                "{runtime_python}",
                "acceptance/probes/strict_parity.py",
                "--gpu",
                "--model",
                model,
                "--models",
                "{models}",
            )
            + ("--out", "{out}/parity.json"),
            hosts=LINUX_GPU,
            env=GPU + PROBE_PATH,
            expect="PARITY OK",
            timeout=3600,
            gpu=True,
        )
        for model in ("qwen", "smol", "tiny")
    ],
    Check(
        "strict-parity-qwen-native",
        "gpu",
        ("{runtime_python}", "acceptance/native_python.py", "acceptance/probes/strict_parity.py", "--gpu")
        + ("--model", "qwen", "--models", "{models}", "--out", "{out}/parity.json"),
        hosts=("3060-native",),
        env=GPU + PROBE_PATH,
        expect="PARITY OK",
        timeout=3600,
        gpu=True,
    ),
    # perf
    Check(
        "strict-throughput",
        "perf",
        ("{runtime_python}", "acceptance/probes/strict_throughput.py", "--gpu", "--models", "{models}")
        + ("--out", "{out}/throughput.json"),
        hosts=("local", "3060-wsl"),
        env=GPU + PROBE_PATH,
        expect="THROUGHPUT OK",
        timeout=3600,
        gpu=True,
    ),
    Check(
        "int8-memory",
        "perf",
        ("{runtime_python}", "acceptance/probes/int8_memory.py", "--gpu", "--model", "{models}/qwen", "--out", "{out}"),
        hosts=("local", "3060-wsl"),
        env=GPU + PROBE_PATH,
        expect="INT8 MEMORY OK",
        timeout=3600,
        gpu=True,
    ),
    Check(
        "strict-phase-trace",
        "perf",
        ("{runtime_python}", "acceptance/probes/strict_phase_trace.py", "--gpu", "--model", "{models}/qwen")
        + ("--pairs", "6", "--out", "{out}/phase-trace.json"),
        hosts=("local", "3060-wsl"),
        env=GPU + PROBE_PATH,
        expect="STRICT PHASE TRACE PASS",
        timeout=3600,
        gpu=True,
    ),
    # faults: the end-to-end strict run on two GPUs (local 5070 Ti and Thao's 3060 over SSH), then the same run with the
    # local worker killed while it holds a lease; both must give the same children and generation records
    Check(
        "strict-e2e",
        "faults",
        (
            "bash",
            "-c",
            '"$1" acceptance/probes/strict_e2e.py --out "$2/plain" --generations 4 && "$1" acceptance/probes/strict_e2e.py'
            ' --out "$2/fault" --generations 4 --kill-local-at 2 --compare "$2/plain/report.json"',
        )
        + ("e2e", "{python}", "{out}"),
        env=GPU,
        expect="E2E OK",
        timeout=2 * 3600,
        gpu=True,
    ),
    Check(
        "strict-e2e-int8",
        "faults",
        ("{python}", "acceptance/probes/strict_e2e.py", "--out", "{out}/int8", "--generations", "4", "--int8-lora")
        + ("--sigma", "0.02"),
        env=GPU,
        expect="E2E OK",
        timeout=2 * 3600,
        gpu=True,
    ),
    # package
    Check(
        "package-linux",
        "package",
        (
            "bash",
            "-c",
            'scripts/build-apps.sh --check "$1/build" && python3 acceptance/probes/package_bytes.py "$1/build"',
        )
        + ("package", "{out}"),
        expect="PACKAGE BYTES OK",
        timeout=3600,
    ),
    # mutation: every registered group must kill all of its mutants
    Check(
        "mutation-strict-routes",
        "mutation",
        ("{python}", "scripts/mutation-check.py", "--repo", "runtime", "--copy", "src", "--copy", "pyproject.toml")
        + tuple(
            x
            for f in ("test_strict_decoder", "test_integer_tma", "test_attention_key_stages", "test_request_context")
            for x in ("--copy", f"tests/eval/{f}.py")
        )
        + ("--env", "PYTHONPATH=src:tests/eval", "--env", "HETEROES_GPU_ACCEPTANCE=1", "--scratch", "{out}")
        + ("--mutants", "acceptance/mutants/strict-routes.json", "--test")
        + (
            "{runtime_python} -m pytest -q -x -p no:cacheprovider tests/eval/test_integer_tma.py "
            "tests/eval/test_attention_key_stages.py tests/eval/test_request_context.py",
        ),
        timeout=4 * 3600,
        gpu=True,
    ),
    Check(
        "mutation-watchdog",
        "mutation",
        ("{python}", "scripts/mutation-check.py", "--repo", "runtime", "--copy", "src", "--copy", "pyproject.toml")
        + ("--copy", "tests/ledger", "--copy", "tests/v3", "--env", "PYTHONPATH=src:tests/ledger:tests/v3")
        + ("--scratch", "{out}", "--mutants", "acceptance/mutants/watchdog.json", "--test")
        + (
            "{runtime_python} -m pytest -q -x -p no:cacheprovider tests/ledger/test_stage_watchdog.py "
            "tests/v3/test_v3_progress.py",
        ),
        timeout=3600,
    ),
    Check(
        "mutation-restore-recovery",
        "mutation",
        ("{python}", "scripts/mutation-check.py", "--repo", "runtime", "--copy", "src", "--copy", "pyproject.toml")
        + ("--copy", "tests/ledger", "--copy", "tests/v3", "--env", "PYTHONPATH=src:tests/ledger:tests/v3")
        + ("--scratch", "{out}", "--mutants", "acceptance/mutants/restore-recovery.json", "--test")
        + (
            "{runtime_python} -m pytest -q -x -p no:cacheprovider tests/ledger/test_restore_recovery.py "
            "tests/ledger/test_run_supervisor.py tests/v3/test_v3_progress.py",
        ),
        timeout=3600,
    ),
    Check(
        "mutation-strict-mismatch",
        "mutation",
        ("{python}", "scripts/mutation-check.py", "--repo", "runtime", "--copy", "src", "--copy", "pyproject.toml")
        + ("--copy", "tests/v3", "--env", "PYTHONPATH=src:tests/v3")
        + ("--scratch", "{out}", "--mutants", "acceptance/mutants/strict-mismatch.json", "--test")
        + (
            "{runtime_python} -m pytest -q -x -p no:cacheprovider tests/v3/test_audit_guard_integration.py "
            "tests/v3/test_audit_guard.py",
        ),
        timeout=3600,
    ),
    Check(
        "mutation-audit-outcomes",
        "mutation",
        ("{python}", "scripts/mutation-check.py", "--repo", "runtime", "--copy", "src", "--copy", "pyproject.toml")
        + ("--copy", "scripts", "--copy", "tests/v3", "--env", "PYTHONPATH=src:tests/v3")
        + ("--scratch", "{out}", "--mutants", "acceptance/mutants/audit-outcomes.json", "--test")
        + (
            "{runtime_python} -m pytest -q -x -p no:cacheprovider tests/v3/test_audit_outcomes.py "
            "tests/v3/test_v3_audit.py tests/v3/test_audit_states.py",
        ),
        timeout=3600,
    ),
    Check(
        "mutation-recovery-io",
        "mutation",
        ("{python}", "scripts/mutation-check.py", "--repo", "runtime", "--copy", "src", "--copy", "pyproject.toml")
        + ("--copy", "scripts", "--copy", "tests/ledger", "--copy", "tests/v3")
        + ("--env", "PYTHONPATH=src:tests/ledger:tests/v3")
        + ("--scratch", "{out}", "--mutants", "acceptance/mutants/recovery-io.json", "--test")
        + (
            "{runtime_python} -m pytest -q -x -p no:cacheprovider tests/ledger/test_cloud_sync.py "
            "tests/ledger/test_recovery_points.py tests/v3/test_v3_recovery.py -k 'not download_restore_cli'",
        ),
        timeout=3600,
    ),
    Check(
        "mutation-strict-decoder",
        "mutation",
        ("{python}", "scripts/mutation-check.py", "--repo", "runtime", "--copy", "src", "--copy", "pyproject.toml")
        + ("--copy", "tests/v3", "--env", "PYTHONPATH=src:tests/v3", "--env", "HETEROES_GPU_ACCEPTANCE=1")
        + ("--scratch", "{out}", "--mutants", "acceptance/mutants/strict-decoder.json", "--test")
        + ("{runtime_python} -m pytest -q -x -p no:cacheprovider tests/v3/test_v3_strict_decoder.py",),
        timeout=3600,
        gpu=True,
    ),
    Check(
        "mutation-strict-qualification-runtime",
        "mutation",
        ("{python}", "scripts/mutation-check.py", "--repo", "runtime", "--copy", "src", "--copy", "pyproject.toml")
        + ("--copy", "tests/v3", "--copy", "tests/ledger")
        + ("--env", "PYTHONPATH=src:tests/v3:tests/ledger", "--env", "HETEROES_GPU_ACCEPTANCE=1")
        + ("--scratch", "{out}", "--mutants", "acceptance/mutants/strict-qualification-runtime.json", "--test")
        + (
            "{runtime_python} -m pytest -q -x -p no:cacheprovider tests/v3/test_model_qualification.py "
            "tests/v3/test_model_probe_process.py tests/ledger/test_model_probe_agent.py",
        ),
        timeout=3600,
        gpu=True,
    ),
    Check(
        "mutation-strict-qualification-backend",
        "mutation",
        ("{python}", "scripts/mutation-check.py", "--repo", ".", "--copy", "backend", "--copy", "runtime/src")
        + ("--copy", "pyproject.toml", "--env", "CUDA_VISIBLE_DEVICES=")
        + ("--scratch", "{out}", "--mutants", "acceptance/mutants/strict-qualification-backend.json", "--test")
        + (
            "{repo}/.venv-backend/bin/python -m pytest -q -x -p no:cacheprovider backend/tests/test_model_qualification.py",
        ),
        timeout=3600,
    ),
    Check(
        "mutation-gpu-ownership-backend",
        "mutation",
        ("{python}", "scripts/mutation-check.py", "--repo", ".", "--copy", "backend", "--copy", "runtime/src")
        + ("--copy", "pyproject.toml", "--env", "CUDA_VISIBLE_DEVICES=")
        + ("--scratch", "{out}", "--mutants", "acceptance/mutants/gpu-ownership-backend.json", "--test")
        + (
            "{repo}/.venv-backend/bin/python -m pytest -q -x -p no:cacheprovider backend/tests/test_model_qualification.py",
        ),
        timeout=3600,
    ),
    Check(
        "mutation-int8-lora",
        "mutation",
        ("{python}", "scripts/mutation-check.py", "--repo", "runtime", "--copy", "src", "--copy", "pyproject.toml")
        + ("--copy", "tests/v3", "--env", "PYTHONPATH=src:tests/v3", "--env", "HETEROES_GPU_ACCEPTANCE=1")
        + ("--scratch", "{out}", "--mutants", "acceptance/mutants/int8-lora.json", "--test")
        + ("{runtime_python} -m pytest -q -x -p no:cacheprovider tests/v3/test_v3_int8_lora.py",),
        timeout=3600,
        gpu=True,
    ),
    Check(
        "mutation-gpu-ownership-runtime",
        "mutation",
        ("{python}", "scripts/mutation-check.py", "--repo", "runtime", "--copy", "src", "--copy", "pyproject.toml")
        + ("--copy", "tests/v3", "--env", "PYTHONPATH=src:tests/v3", "--env", "HETEROES_GPU_ACCEPTANCE=1")
        + ("--scratch", "{out}", "--mutants", "acceptance/mutants/gpu-ownership-runtime.json", "--test")
        + (
            "{runtime_python} -m pytest -q -x -p no:cacheprovider tests/v3/test_v3_strict_decoder.py "
            "tests/v3/test_sdk_lab.py",
        ),
        timeout=3600,
        gpu=True,
    ),
]

SUITE = ("strict-gpu-suite", "strict-gpu-suite@3060-wsl", "strict-gpu-suite-native@3060-native")
PARITY = (
    "strict-parity-qwen",
    "strict-parity-qwen@3060-wsl",
    "strict-parity-qwen-native@3060-native",
    "strict-parity-smol",
    "strict-parity-smol@3060-wsl",
    "strict-parity-tiny",
    "strict-parity-tiny@3060-wsl",
)

GATES = [
    # M0 — contract and baseline
    Gate("M0.contract", "M0", "ADR-012, numerical contract and CPU checks", checks=("check-all",)),
    Gate(
        "M0.stage-trace",
        "M0",
        "stage timing of the strict worker path (load, engine, perturb, rollout, restore) on trained Qwen",
        checks=("strict-phase-trace", "strict-phase-trace@3060-wsl"),
    ),
    Gate(
        "M0.memory-map",
        "M0",
        "CUDA peak per phase, live FP16 weights, strict engine buffers, CPU snapshot and host peak",
        checks=("strict-phase-trace", "strict-phase-trace@3060-wsl"),
    ),
    # M1 — one-model strict backend
    Gate("M1.operators", "M1", "G0/G1 operators and kernels on SM120, SM86 Linux and native Windows", checks=SUITE),
    Gate("M1.decoder", "M1", "G2 trained parent/canonical ±/restore/EOS parity on three hosts", checks=PARITY),
    Gate("M1.throughput", "M1", "G3 throughput floor and golden tokens", checks=("strict-throughput",)),
    Gate("M1.mutation", "M1", "promoted execution routes kill all mutants", checks=("mutation-strict-routes",)),
    Gate(
        "M1.executor-cross-host",
        "M1",
        "strict_b22_v1 executor tests pass on the 3060 (WSL2 and native Windows)",
        checks=("strict-gpu-suite@3060-wsl", "strict-gpu-suite-native@3060-native"),
    ),
    Gate(
        "M1.executor",
        "M1",
        "strict_b22_v1 through the candidate executor: live weights, restore, chunk invariance, failure mapping",
        checks=("strict-gpu-suite", "mutation-strict-decoder"),
    ),
    Gate(
        "M1.architectures",
        "M1",
        "Turing, Ada and Hopper execution",
        deferred="Only SM86 (RTX 3060) and SM120 (RTX 5070 Ti) are available; other architectures are compiled and "
        "audited only.",
    ),
    # M2 — delivery, scorer, audit, watchdog, recovery
    Gate(
        "M2.delivery", "M2", "durable outbox, scorer reservation, usage queue, audit accounting", checks=("check-all",)
    ),
    Gate(
        "M2.watchdog",
        "M2",
        "D11 stage-progress watchdog, explicit finite hard cap that survives restarts",
        checks=("check-all", "mutation-watchdog"),
    ),
    Gate(
        "M2.restore-recovery",
        "M2",
        "D10 one automatic restore recovery per worker and run",
        checks=("check-all", "mutation-restore-recovery"),
    ),
    Gate(
        "M2.strict-mismatch",
        "M2",
        "D9 stop before the next update on a strict audit mismatch",
        checks=("check-all", "mutation-strict-mismatch"),
    ),
    Gate(
        "M2.audit-ui",
        "M2",
        "audit outcomes in supervisor, backend and UI (fixture browser check in check-all)",
        checks=("check-all", "mutation-audit-outcomes"),
    ),
    # M3 — recovery I/O and long-run cost
    Gate(
        "M3.streaming-upload",
        "M3",
        "bounded streaming recovery upload (hash-checked) with stateful backoff",
        checks=("check-all", "mutation-recovery-io"),
    ),
    Gate(
        "M3.verify-cache",
        "M3",
        "verification cache bound to manifest and file identity",
        checks=("check-all", "mutation-recovery-io"),
    ),
    Gate(
        "M3.retention",
        "M3",
        "retention keeps the newest cloud-verified point and the paused checkpoint",
        checks=("check-all", "mutation-recovery-io"),
    ),
    Gate(
        "M3.bookkeeping",
        "M3",
        "early/middle/late per-generation cost",
        open="The growth of per-generation bookkeeping (1.7 s to 11 s over 600 generations) is not explained or fixed.",
    ),
    Gate(
        "M3.full-disk",
        "M3",
        "acceptance on a really full disk",
        deferred="Deferred by the owner's operations decision of 2026-10-23 (Q4); simulated faults do not replace it.",
    ),
    # M4 — product, lifecycle, packaging
    Gate(
        "M4.identity",
        "M4",
        "backend identity in recipes without changing historical hashes",
        # ADR-013: `evaluation.decoder = "strict_b22_v1"`; golden identities (check-all) keep every recorded hash
        checks=("check-all", "mutation-strict-decoder"),
    ),
    Gate(
        "M4.qualification",
        "M4",
        "qualification keyed by backend and contract",
        checks=("check-all", "mutation-strict-qualification-runtime", "mutation-strict-qualification-backend"),
    ),
    Gate(
        "M4.gpu-ownership",
        "M4",
        "D1 one weight set per GPU across worker, audit, validation and export",
        # strict runs only (ADR-013 amendment): coordinator on its own GPU, export reload after the live set leaves it;
        # earlier recipes keep their FP32 shadow and layouts
        checks=("check-all", "strict-gpu-suite", "mutation-gpu-ownership-backend", "mutation-gpu-ownership-runtime"),
    ),
    Gate("M4.packaging", "M4", "Linux Worker/Server packages carry the exact runtime", checks=("package-linux",)),
    Gate(
        "M4.default",
        "M4",
        "B22 is the default for new GPU runs",
        # the lab form (web-experiments browser check in check-all); the SDK stays explicit (ADR-013 amendment)
        checks=("check-all",),
    ),
    # M5 — system acceptance
    Gate(
        "M5.end-to-end",
        "M5",
        "coordinator and two machines, strict backend, faults",
        checks=("strict-e2e",),
    ),
    Gate(
        "M5.long-run",
        "M5",
        "system soak across early/middle/late generations",
        open="No long strict soak run has been made.",
    ),
    Gate(
        "M5.release",
        "M5",
        "release with rollback, deployed",
        open="No release artifact and rollback rehearsal exist yet.",
    ),
    # M6 — quantized frozen base + LoRA
    Gate("M6.int8-oracle", "M6", "frozen int8 format, CPU oracle and CUDA kernels", checks=("check-all", *SUITE[:2])),
    Gate(
        "M6.lora-lifecycle",
        "M6",
        "int8 frozen base + LoRA through the whole lifecycle",
        # strict_int8_lora_v1 (ADR-014): standalone/SDK runs; the lab does not offer it yet
        checks=("mutation-int8-lora", "strict-e2e-int8", "int8-memory", "int8-memory@3060-wsl"),
    ),
]
