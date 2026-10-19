"""Pinned safetensors file manifests; no executable remote model code."""

import hashlib
from pathlib import Path, PurePosixPath
import re
from .data import sha

SUPPORTED_MODELS = (
    "Qwen/Qwen2.5-0.5B-Instruct",
    "HuggingFaceTB/SmolLM2-360M-Instruct",
    "TinyLlama/TinyLlama-1.1B-Chat-v1.0",
)


def validate(manifest):
    if (
        set(manifest) != {"formatVersion", "modelId", "revision", "tokenizerRevision", "format", "files"}
        or manifest["formatVersion"] != 1
    ):
        raise ValueError("Invalid pinned model manifest")
    if manifest["modelId"] not in SUPPORTED_MODELS:
        raise ValueError("Unsupported text model family")
    if manifest["format"] != "safetensors":
        raise ValueError("Only safetensors checkpoints are accepted")
    if not all(
        isinstance(manifest[k], str) and re.fullmatch("[a-f0-9]{40}", manifest[k])
        for k in ("revision", "tokenizerRevision")
    ):
        raise ValueError("Pin exact model and tokenizer commits")
    if manifest["revision"] != manifest["tokenizerRevision"]:
        raise ValueError("Tokenizer must come from the same pinned snapshot")
    files = manifest["files"]
    if not isinstance(files, dict) or not 2 <= len(files) <= 200 or "config.json" not in files:
        raise ValueError("Missing pinned model files")
    if not any(name.endswith(".safetensors") for name in files):
        raise ValueError("Missing safetensors weights")
    if not any(name in files for name in ("tokenizer.json", "tokenizer.model")):
        raise ValueError("Missing tokenizer")
    for name, digest in files.items():
        path = PurePosixPath(name)
        if (
            path.is_absolute()
            or ".." in path.parts
            or "\\" in name
            or not name
            or path.as_posix() != name
            or path.suffix not in (".json", ".safetensors", ".model", ".txt", ".tiktoken", ".jinja")
            or not isinstance(digest, str)
            or not re.fullmatch("[a-f0-9]{64}", digest)
        ):
            raise ValueError("Unsafe model file manifest")
    return manifest


def inspect(path, model_id, revision):
    path = Path(path)
    files = {}
    for file in sorted(path.rglob("*")):
        if file.is_file() and file.suffix in (".json", ".safetensors", ".model", ".txt", ".tiktoken", ".jinja"):
            with file.open("rb") as stream:
                files[file.relative_to(path).as_posix()] = hashlib.file_digest(stream, "sha256").hexdigest()
    return validate(
        {
            "formatVersion": 1,
            "modelId": model_id,
            "revision": revision,
            "tokenizerRevision": revision,
            "format": "safetensors",
            "files": files,
        }
    )


def verify(path, manifest):
    validate(manifest)
    root = Path(path)
    # Reject alternate weight/config files that Transformers might choose even
    # though the expected files themselves are valid.
    actual = {
        p.relative_to(root).as_posix()
        for p in root.rglob("*")
        if p.is_file() and p.suffix in (".json", ".safetensors", ".model", ".txt", ".tiktoken", ".jinja", ".bin", ".py")
    }
    if actual != set(manifest["files"]):
        raise ValueError("Model file set differs from pinned manifest")
    for name, expected in manifest["files"].items():
        with (root / name).open("rb") as stream:
            if hashlib.file_digest(stream, "sha256").hexdigest() != expected:
                raise ValueError("Model file checksum mismatch")
    return sha(manifest)


def load(path, manifest, device):
    verify(path, manifest)
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    from heteroes.model.loading import LoadedModel
    from heteroes.model.schema import build_parameter_schema

    model = AutoModelForCausalLM.from_pretrained(
        path, dtype=torch.float16, local_files_only=True, trust_remote_code=False, use_safetensors=True
    ).to(device)
    tokenizer = AutoTokenizer.from_pretrained(path, local_files_only=True, trust_remote_code=False)
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token = tokenizer.eos_token
    return LoadedModel(
        model,
        tokenizer,
        build_parameter_schema(model),
        manifest["revision"],
        model.generation_config.to_dict(),
        device,
        manifest["modelId"],
    )
