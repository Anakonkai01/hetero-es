"""
Models of Recipe v3: any local safetensors causal LM, pinned by the SHA-256 of its files (no list of model names; ADR-008
section 2), loaded in FP16 without remote code, with the trainable schema of the recipe's weight space.
"""

import hashlib
from pathlib import Path

LOADABLE = (".json", ".safetensors", ".model", ".txt", ".tiktoken", ".jinja")


def registration_manifest(path, model_id, revision):
    """The web lab's pinned registration document, built from the same safe files a v3 run loads."""
    from heteroes.study.models import validate

    return validate(
        {
            "formatVersion": 1,
            "modelId": model_id,
            "revision": revision,
            "tokenizerRevision": revision,
            "format": "safetensors",
            "files": file_manifest(path),
        },
        allow_any=True,
    )


def file_manifest(path) -> dict:
    """{relative name: sha256} of the files of a model directory; refuses code and pickled weights."""
    root = Path(path)
    if any(p.suffix in (".py", ".bin", ".pt", ".pkl") for p in root.rglob("*") if p.is_file()):
        raise ValueError("the model directory holds code or pickled weights: only safetensors models are accepted")
    files = {}
    for file in sorted(root.rglob("*")):
        if file.is_file() and file.suffix in LOADABLE:
            with file.open("rb") as stream:
                files[file.relative_to(root).as_posix()] = hashlib.file_digest(stream, "sha256").hexdigest()
    if not any(name.endswith(".safetensors") for name in files) or "config.json" not in files:
        raise ValueError("a model directory needs config.json and safetensors weights")
    return files


def load(path, files, device="cpu"):
    """(model, tokenizer) after checking that the directory is exactly the pinned files."""
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    from heteroes.study.models import verify_files

    verify_files(path, files)
    model = AutoModelForCausalLM.from_pretrained(
        path, dtype=torch.float16, local_files_only=True, trust_remote_code=False, use_safetensors=True
    ).to(device)
    tokenizer = AutoTokenizer.from_pretrained(path, local_files_only=True, trust_remote_code=False)
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token = tokenizer.eos_token
    model.eval()
    return model, tokenizer


def trainable_schema(model, weight_space, adapter_file=None):
    """
    The schema that ES perturbs and updates for this weight space. For LoRA the adapters are attached first (in place) and,
    when `adapter_file` is given, loaded from it: its SHA-256 must be the recipe's `initialAdapterSha256`.
    """
    from heteroes.model.schema import build_parameter_schema, select_parameters

    kind = weight_space["kind"]
    if kind == "full":
        return build_parameter_schema(model)
    if kind == "subset":
        return select_parameters(build_parameter_schema(model), weight_space["include"])
    if kind == "lora":
        from heteroes.model.lora import attach_lora, load_adapter_
        from heteroes.model.lora import trainable_schema as adapter_schema

        attach_lora(model, weight_space, seed=0)  # replaced by the pinned initial adapter just below
        if adapter_file is None:
            raise ValueError("a LoRA run loads its pinned initial adapter")
        load_adapter_(model, adapter_file, weight_space["initialAdapterSha256"])
        return adapter_schema(model)
    raise ValueError(f"unknown weight space {kind!r}")
