"""
The LoRA weight space of Recipe v3 (ADR-008 section 4).

The base model stays FP16 and frozen (the recipe pins its files); LoRA adapters are injected into the target modules with
PEFT, in FP16, and the TRAINABLE schema is the subset of the model's parameter schema made of the `lora_A`/`lora_B`
tensors. Noise, perturbation, restore, update and the weights files then work on the adapters with the unchanged code.

Workers never initialize adapters at random: the initial adapter is a weights file made once from a seed
(`create_initial_adapter`) and named by its SHA-256 in the recipe. `export_peft` writes the adapters in the PEFT format
(`adapter_config.json` + `adapter_model.safetensors`), loadable with `PeftModel.from_pretrained` on the same base model.

LoRA is another search distribution than full-parameter ES (the step of W is the product of two perturbed factors):
its results are never compared on one chart with full-parameter runs (owner decision 5).
"""

import json
from pathlib import Path

import torch

from heteroes.model.schema import build_parameter_schema, select_parameters
from heteroes.model.weights_io import load_weights_, write_weights

ADAPTER_PATTERN = r"\.lora_[AB]\."
# what the PEFT configuration needs; the recipe also pins `initialAdapterSha256`, which exists only once the adapter is made
SPACE_KEYS = {"kind", "rank", "alpha", "targetModules"}


def _config(space):
    from peft import LoraConfig

    if not isinstance(space, dict) or space.get("kind") != "lora" or not SPACE_KEYS <= set(space):
        raise ValueError("a LoRA weight space names kind, rank, alpha and targetModules")
    return LoraConfig(
        r=space["rank"],
        lora_alpha=space["alpha"],
        target_modules=sorted(space["targetModules"]),
        lora_dropout=0.0,
        bias="none",
        init_lora_weights=True,  # A: Kaiming-uniform from the torch generator, B: zeros (PEFT's default)
        use_rslora=False,
        use_dora=False,
    )


def attach_lora(model, space, seed: int):
    """Inject FP16 LoRA adapters into `model` (in place) and return it. The adapters are initialized from `seed` without
    touching the caller's random state; a worker then loads the recipe's initial adapter over them (`load_adapter_`)."""
    from peft import inject_adapter_in_model

    if any(p.dtype != torch.float16 for p in model.parameters()):
        raise TypeError("LoRA is attached to an FP16 base model")
    if any(".lora_" in name for name, _ in model.named_parameters()):
        raise ValueError("the model already has LoRA adapters")
    config = _config(space)
    with torch.random.fork_rng(devices=[]):
        torch.manual_seed(seed)
        inject_adapter_in_model(config, model)
    with torch.no_grad():
        for name, parameter in model.named_parameters():
            if ".lora_" in name:
                parameter.data = parameter.data.to(torch.float16)
    return model


def trainable_schema(model):
    """The subset schema of the adapters: what is perturbed, updated, restored, hashed and published."""
    schema = select_parameters(build_parameter_schema(model), [ADAPTER_PATTERN])
    if not all(".lora_" in entry.canonical_name for entry in schema.entries):
        raise ValueError("the adapter schema selected a base parameter")
    return schema


def create_initial_adapter(model, space, seed: int, path) -> str:
    """Attach adapters initialized from `seed` and write them to `path`; returns the file's SHA-256 (the recipe's
    `initialAdapterSha256`)."""
    attach_lora(model, space, seed)
    return write_weights(model, trainable_schema(model), path)


def load_adapter_(model, path, expected_sha256: str) -> None:
    """Load an adapter file into a model that has the adapters attached; the file's size and hash are checked first."""
    load_weights_(model, trainable_schema(model), path, expected_sha256)


def export_peft(model, space, directory, base_model_id: str, revision: str) -> Path:
    """Write the adapters as a PEFT adapter directory for `base_model_id` at `revision`."""
    from peft import get_peft_model_state_dict
    from safetensors.torch import save_file

    config = _config(space)
    if not any(".lora_" in name for name, _ in model.named_parameters()):
        raise ValueError("the model has no LoRA adapters to export")  # checked before anything is written
    state = get_peft_model_state_dict(model)
    if not state or not all(".lora_" in key for key in state):
        raise ValueError("the PEFT state of the model holds something other than LoRA adapters")
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    config.base_model_name_or_path = base_model_id
    config.revision = revision
    config.save_pretrained(directory)
    # PeftModel.save_pretrained prefixes the keys with the wrapper's path; an injected model has no wrapper
    tensors = {f"base_model.model.{key}": tensor.detach().contiguous().cpu() for key, tensor in state.items()}
    save_file(tensors, directory / "adapter_model.safetensors", metadata={"format": "pt"})
    json.loads((directory / "adapter_config.json").read_text())  # written by PEFT: it must be readable JSON
    return directory
