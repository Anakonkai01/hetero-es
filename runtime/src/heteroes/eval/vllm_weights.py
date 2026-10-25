"""Experimental HF-named ES views over unquantized, single-rank vLLM weight storage.

No vLLM import or second inference model is needed. The temporary HF model is on meta; the returned
parameter-only module shares every weight with the serving owner. It has no inference forward method.
This maps storage and preserves canonical noise addresses; it makes no vendor arithmetic/quality claim.
"""

import torch

from heteroes.eval.reference_ops import ReferenceArithmeticError

VLLM_VIEW_VERSION = "hf_parameter_views_over_vllm_fused_fp16_v1_experimental"


def hf_parameter_view(owner, config):
    """Return canonical HF parameter names/shapes/aliases over supported live fused FP16 matrices.

    Only dense Qwen2/Llama/Mistral layouts are admitted. Sharding, quantized/repacked weights,
    unconsumed parameters and inconsistent ties fail; owner parameters are never rebound or copied.
    Padded vocabulary rows remain outside the canonical HF parameter view.
    """
    if getattr(config, "model_type", None) not in ("qwen2", "llama", "mistral"):
        raise ReferenceArithmeticError("Unsupported vLLM parameter-view family")
    from transformers import AutoModelForCausalLM

    with torch.device("meta"):
        template = AutoModelForCausalLM.from_config(config).half()
    expected = tuple(template.named_parameters(remove_duplicate=False))
    shapes = {name: tuple(p.shape) for name, p in expected}
    sources = dict(owner.named_parameters(remove_duplicate=False))
    used, aliases = set(), {}
    view = torch.nn.Module()

    def source_view(name):
        source_name, offset = name, 0
        source_shape = shapes[name]
        for pieces, packed in (
            (("q_proj", "k_proj", "v_proj"), "qkv_proj"),
            (("gate_proj", "up_proj"), "gate_up_proj"),
        ):
            for i, piece in enumerate(pieces):
                marker = "." + piece + "."
                if marker in name:
                    prefix, field = name.rsplit(marker, 1)
                    source_name = prefix + "." + packed + "." + field
                    sizes = [shapes[prefix + "." + part + "." + field][0] for part in pieces]
                    offset = sum(sizes[:i])
                    source_shape = (sum(sizes), *shapes[name][1:])
        source = sources.get(source_name)
        if (
            source is None
            or source.dtype != torch.float16
            or not source.is_contiguous()
            or source.device.type == "meta"
        ):
            raise ReferenceArithmeticError(f"Missing or incompatible vLLM FP16 storage: {source_name}")
        vocabulary = name in ("model.embed_tokens.weight", "lm_head.weight")
        if tuple(source.shape) != source_shape and not (
            vocabulary
            and source.ndim == 2
            and source.shape[0] >= source_shape[0]
            and tuple(source.shape[1:]) == source_shape[1:]
        ):
            raise ReferenceArithmeticError(f"Sharded or incompatible vLLM parameter shape: {source_name}")
        used.add(source_name)
        return source.detach().narrow(0, offset, shapes[name][0])

    for name, meta in expected:
        tensor = source_view(name)
        if id(meta) in aliases:
            bound = aliases[id(meta)]
            if tensor.data_ptr() != bound.data_ptr() or tuple(tensor.shape) != tuple(bound.shape):
                raise ReferenceArithmeticError(f"Inconsistent vLLM tied parameter: {name}")
        else:
            bound = torch.nn.Parameter(tensor, requires_grad=False)
            aliases[id(meta)] = bound
        parent = view
        parts = name.split(".")
        for part in parts[:-1]:
            if part not in parent._modules:
                parent.add_module(part, torch.nn.Module())
            parent = parent._modules[part]
        parent.register_parameter(parts[-1], bound)
    if set(sources) != used:
        raise ReferenceArithmeticError("Unconsumed vLLM parameters in the proposed HF view")
    return view
