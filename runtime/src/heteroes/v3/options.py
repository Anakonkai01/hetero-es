"""CPU-safe validation of v3 weight spaces and shared-lab settings."""

import math
import re
import struct

from heteroes.v3.scoring import validate_spec

COEFFICIENT_RULES = {"zscore": {1}, "centered-rank": {1}}  # and python@1, on a self-hosted coordinator only
ALPHA_SCHEDULES = ("constant", "cosine", "linear")
# Prompts per generate() call a recipe may declare: FP16 is exact one prompt at a time only; FP32 batches gave the same
# texts as one prompt at a time in the cross-GPU probes (16, and 64 on 5070 Ti, 3060 and 1660S: RUNTIME-TODO chunk-128)
EXACT_CHUNKS = {"float16": (1,), "float32": (16, 32, 64)}
MAX_WINDOW = 8


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


def validate_options(config):
    validate_weight_space(config["weightSpace"], initial_adapter=False)
    validate_spec(config["scorer"], allow_python=False)
    if config["coefficientRule"] not in {
        f"{name}@{v}" for name, versions in COEFFICIENT_RULES.items() for v in versions
    }:
        raise ValueError("unsupported coefficient rule")
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
    if type(config["antithetic"]) is not bool or (config["antithetic"] and config["candidatesPerGeneration"] % 2):
        raise ValueError("antithetic sampling requires an even population")
    if config.get("sampler", "sha256-python-random-sample-v1") not in (
        "sha256-python-random-sample-v1",
        "epoch-shuffle@1",
    ):
        raise ValueError("unknown batch sampler")
    if config["decodeEngine"] != "hf_generate":
        raise ValueError("Recipe v3 uses the HF generate decoder")
    prompt = config["systemPrompt"]
    if prompt is not None and (not isinstance(prompt, str) or not prompt or len(prompt) > 4000):
        raise ValueError("system prompt is null or a text of at most 4000 characters")
