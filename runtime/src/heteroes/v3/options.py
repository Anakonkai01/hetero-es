"""CPU-safe validation of v3 weight spaces and shared-lab settings."""

import math
import hashlib
import re
import struct

from heteroes.v3.scoring import validate_spec

COEFFICIENT_RULES = {"zscore": {1}, "centered-rank": {1}}  # and python@1, on a self-hosted coordinator only
ALPHA_SCHEDULES = ("constant", "cosine", "linear")
# Prompts per generate() call a recipe may declare: FP16 is exact one prompt at a time only; FP32 batches gave the same
# texts as one prompt at a time in the cross-GPU probes (16, and 64 on 5070 Ti, 3060 and 1660S: RUNTIME-TODO chunk-128)
EXACT_CHUNKS = {"float16": (1,), "float32": (16, 32, 64)}
MAX_WINDOW = 8


def validate_audit_rate(value):
    """Operational coverage, independent of numerical recipe/plan identity; zero explicitly disables auditing."""
    if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 1:
        raise ValueError("audit rate must be a finite number between zero and one")
    return float(value)


def audit_selected(candidate_id, rate=0.05):
    """Historical 1/20 hash rule at the default rate; the exact address space at explicit coverage 0..1."""
    validate_audit_rate(rate)
    threshold = 2**256 // 20 if rate == 0.05 else int(rate * 2**256)
    return int(hashlib.sha256(candidate_id.encode()).hexdigest(), 16) < threshold


def validate_prompt_format(value, system_prompt=None):
    selected = "chat" if value is None else value
    if selected not in ("chat", "raw"):
        raise ValueError("promptFormat is chat or raw")
    if selected == "raw" and system_prompt is not None:
        raise ValueError("Raw prompts require systemPrompt null; put instructions in the dataset prompt")
    return selected


def _is_float32(value):
    return struct.unpack("<f", struct.pack("<f", value))[0] == value


def validate_update_rule(rule):
    """None (plain step) or {"kind": "momentum", "beta": float32 in (0, 1), "window": 2..MAX_WINDOW}."""
    if rule is None:
        return rule
    if not isinstance(rule, dict) or set(rule) != {"kind", "beta", "window"} or rule["kind"] != "momentum":
        raise ValueError('an update rule is {"kind": "momentum", "beta": ..., "window": ...}')
    beta, window = rule["beta"], rule["window"]
    if (
        isinstance(beta, bool)
        or not isinstance(beta, (int, float))
        or not math.isfinite(beta)
        or not 0 < beta < 1
        or not _is_float32(beta)
    ):
        raise ValueError("momentum beta is a float32 value strictly between 0 and 1 (for example 0.875)")
    if type(window) is not int or not 2 <= window <= MAX_WINDOW:
        raise ValueError(f"the momentum window is a whole number from 2 to {MAX_WINDOW}")
    return rule


def validate_weight_space(space, *, initial_adapter=True):
    kind = space.get("kind") if isinstance(space, dict) else None
    keys = {"full": {"kind"}, "subset": {"kind", "include"}, "lora": {"kind", "rank", "alpha", "targetModules"}}
    if not isinstance(kind, str) or kind not in keys:
        raise ValueError("unknown weight space")
    expected = keys[kind] | ({"initialAdapterSha256"} if kind == "lora" and initial_adapter else set())
    if set(space) != expected:
        raise ValueError("weight space fields differ from the declared kind")
    if kind == "subset":
        if not isinstance(space["include"], list) or not space["include"]:
            raise ValueError("a subset names at least one pattern")
        for pattern in space["include"]:
            if not isinstance(pattern, str) or not pattern:
                raise ValueError("a subset pattern is a nonempty string")
            try:
                re.compile(pattern)
            except re.error as error:
                raise ValueError(f"invalid subset pattern: {error}") from None
    if kind == "lora":
        if type(space["rank"]) is not int or not 1 <= space["rank"] <= 1024:
            raise ValueError("LoRA rank must be between 1 and 1024")
        if type(space["alpha"]) not in (int, float) or not math.isfinite(space["alpha"]) or space["alpha"] <= 0:
            raise ValueError("LoRA alpha must be finite and positive")
        if (
            not isinstance(space["targetModules"], list)
            or not space["targetModules"]
            or not all(isinstance(m, str) and m for m in space["targetModules"])
        ):
            raise ValueError("LoRA names its target modules")
        if initial_adapter and (
            not isinstance(space["initialAdapterSha256"], str)
            or not re.fullmatch("[a-f0-9]{64}", space["initialAdapterSha256"])
        ):
            raise ValueError("initialAdapterSha256 has the wrong format")
    return space


def validate_seed_namespace(value):
    """Optional namespace for repeatable candidate draws across otherwise distinct runs; absent uses the run ID."""
    if value is not None and (
        not isinstance(value, str) or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}", value) is None
    ):
        raise ValueError("the seed namespace is 1..128 letters, digits or ._:-, starting with a letter or digit")
    return value


PYTHON_ROLES = ("scorer", "coefficients", "sampler")
PYTHON_CODE_KEYS = {"role", "name", "function", "source", "codeSha256"}
MAX_PYTHON_SOURCE = 1_000_000


def validate_python_code(config):
    """
    The researcher code frozen with a web-lab experiment (`pythonCode`): one file per role, each matching the SHA-256 that
    the plan pins (the scorer's codeSha256, or the python@1:<sha> coefficient rule), and nothing that the plan does not use.
    """
    from heteroes.v3.scoring import source_sha256

    entries = config.get("pythonCode", [])
    if not isinstance(entries, list) or len({e.get("role") for e in entries if isinstance(e, dict)}) != len(entries):
        raise ValueError("pythonCode is a list with at most one file per role")
    wanted = {}
    if config["scorer"]["kind"] == "python":
        wanted["scorer"] = config["scorer"]["codeSha256"]
    if config["coefficientRule"].startswith("python@1:"):
        wanted["coefficients"] = config["coefficientRule"].removeprefix("python@1:")
    if str(config.get("sampler", "")).startswith("python@1:"):
        wanted["sampler"] = config["sampler"].removeprefix("python@1:")
    found = {}
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != PYTHON_CODE_KEYS or entry["role"] not in PYTHON_ROLES:
            raise ValueError(f"a pythonCode entry has exactly the keys {sorted(PYTHON_CODE_KEYS)}")
        if not isinstance(entry["name"], str) or not re.fullmatch(
            r"[A-Za-z0-9_][A-Za-z0-9_.-]{0,99}\.py", entry["name"]
        ):
            raise ValueError("a Python code file is named like reward.py")
        if not isinstance(entry["function"], str) or not entry["function"].isidentifier():
            raise ValueError("a Python function name is an identifier")
        if not isinstance(entry["source"], str) or not 0 < len(entry["source"].encode()) <= MAX_PYTHON_SOURCE:
            raise ValueError(f"a Python code file has 1 to {MAX_PYTHON_SOURCE} bytes")
        if source_sha256(entry["name"], entry["source"].encode()) != entry["codeSha256"]:
            raise ValueError("Python code does not match its SHA-256")
        found[entry["role"]] = entry["codeSha256"]
    if found != wanted:
        raise ValueError("pythonCode must be exactly the code the scorer, coefficient rule and sampler pin")


def validate_options(config, *, allow_python=False, with_code=True):
    """
    A web-lab configuration. `allow_python` admits a Python scorer and coefficient rule: with their frozen code (the lab
    and the coordinator), or, `with_code=False`, without it (a worker, which never receives researcher code).
    """
    validate_audit_rate(config.get("auditRate", 0.05))
    validate_prompt_format(config.get("promptFormat"), config.get("systemPrompt"))
    validate_seed_namespace(config.get("candidateSeedNamespace"))
    validate_weight_space(config["weightSpace"], initial_adapter=False)
    validate_spec(config["scorer"], allow_python=allow_python)
    python_rule = allow_python and re.fullmatch("python@1:[0-9a-f]{64}", str(config["coefficientRule"]))
    if not python_rule and config["coefficientRule"] not in {
        f"{name}@{v}" for name, versions in COEFFICIENT_RULES.items() for v in versions
    }:
        raise ValueError("unsupported coefficient rule")
    if allow_python and with_code:
        validate_python_code(config)
    elif "pythonCode" in config:
        raise ValueError("this configuration may not carry Python code")
    if config.get("alphaSchedule", "constant") not in ALPHA_SCHEDULES:
        raise ValueError(f"alpha schedule is one of {ALPHA_SCHEDULES}")
    if config.get("alphaMinimum") is not None and config["alphaMinimum"] > config["alpha"]:
        raise ValueError("the minimum alpha exceeds alpha")
    if config.get("momentumBeta") is not None:
        validate_update_rule(
            {"kind": "momentum", "beta": config["momentumBeta"], "window": config.get("momentumWindow", 4)}
        )
    if (
        config.get("evalChunk") is not None
        and config["evalChunk"] not in EXACT_CHUNKS[config.get("evalDtype", "float32")]
    ):
        raise ValueError("unsupported prompts per generate() call")
    if config.get("evalChunks") is not None and (
        not isinstance(config["evalChunks"], list)
        or not config["evalChunks"]
        or any(c not in EXACT_CHUNKS[config.get("evalDtype", "float32")] for c in config["evalChunks"])
        or config.get("evalChunk") not in config["evalChunks"]
    ):
        raise ValueError("evalChunks lists exact chunks and includes evalChunk")
    if type(config["antithetic"]) is not bool or (config["antithetic"] and config["candidatesPerGeneration"] % 2):
        raise ValueError("antithetic sampling requires an even population")
    sampler = config.get("sampler", "sha256-python-random-sample-v1")
    if sampler not in ("sha256-python-random-sample-v1", "epoch-shuffle@1") and not (
        allow_python and re.fullmatch("python@1:[0-9a-f]{64}", str(sampler))
    ):
        raise ValueError("unknown batch sampler")
    from heteroes.catalog import CPU_GUARD_DECODER, V3_DECODE_ENGINES

    if config["decodeEngine"] not in V3_DECODE_ENGINES:
        raise ValueError("unknown Recipe v3 decoder")
    if config["decodeEngine"] == CPU_GUARD_DECODER and config.get("evalDtype", "float32") != "float32":
        raise ValueError("The CPU-guard decoder requires FP32 evaluation")
    prompt = config["systemPrompt"]
    if prompt is not None and (not isinstance(prompt, str) or not prompt or len(prompt) > 4000):
        raise ValueError("system prompt is null or a text of at most 4000 characters")
