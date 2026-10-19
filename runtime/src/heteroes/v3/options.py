"""CPU-safe validation of v3 weight spaces and shared-lab settings."""

import math
import re

from heteroes.v3.scoring import validate_spec

COEFFICIENT_RULES = {"zscore": {1}, "centered-rank": {1}}  # and python@1, on a self-hosted coordinator only


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
    if type(config["antithetic"]) is not bool or (config["antithetic"] and config["candidatesPerGeneration"] % 2):
        raise ValueError("antithetic sampling requires an even population")
    if config["decodeEngine"] != "hf_generate":
        raise ValueError("Recipe v3 uses the HF generate decoder")
    prompt = config["systemPrompt"]
    if prompt is not None and (not isinstance(prompt, str) or not prompt or len(prompt) > 4000):
        raise ValueError("system prompt is null or a text of at most 4000 characters")
