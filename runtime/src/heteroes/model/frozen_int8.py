"""Typed frozen-int8 base storage with FP16 LoRA adapters for the M6 experiment.

The projections targeted here keep only the pinned int8 rows, FP32 row scales and an optional frozen FP16 bias.
There is no dequantized ``weight`` parameter. Only ``lora_A``/``lora_B`` tensors are parameters; the ES code
selects them through the unchanged canonical schema. Embeddings and a possibly tied LM head stay in the
original FP16 storage; a tied LM head can optionally receive sidecar int8 storage without breaking the tie.

This is experimental storage, not a managed recipe. The CPU forward is an oracle; CUDA execution is provided by
``heteroes.eval.frozen_int8_cuda``. The adapter delta uses the strict pairwise FP32 operator contract on the
widened FP16 factors; it is not part of the exact-integer base projection but is bit-identical across the
reference and CUDA kernels that implement that contract.
"""

from __future__ import annotations

import hashlib
import math
from pathlib import Path

import torch
import torch.nn as nn

from heteroes.eval import frozen_int8
from heteroes.eval import reference_ops as ops
from heteroes.eval.reference_ops import ReferenceArithmeticError
from heteroes.model.lora import load_adapter_, trainable_schema
from heteroes.model.weights_io import write_weights

FROZEN_LORA_VERSION = frozen_int8.ADAPTER_STORAGE_VERSION
DEFAULT_TARGETS = ("q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj")


def _adapter_seed(seed, name):
    if type(seed) is not int:
        raise ReferenceArithmeticError("A LoRA seed must be an integer")
    digest = hashlib.sha256(f"{seed}:{name}".encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "little") & 0x7FFFFFFF


def _validate_configuration(rank, alpha, adapter_name):
    if type(rank) is not int or rank < 1:
        raise ReferenceArithmeticError("LoRA rank must be a positive integer")
    if not isinstance(alpha, (int, float)) or isinstance(alpha, bool) or not math.isfinite(alpha) or alpha <= 0:
        raise ReferenceArithmeticError("LoRA alpha must be a positive finite number")
    if not isinstance(adapter_name, str) or not adapter_name or "." in adapter_name:
        raise ReferenceArithmeticError("A LoRA adapter name must be a nonempty string without dots")


class FrozenInt8LoraLinear(nn.Module):
    """One frozen int8 base projection plus FP16 LoRA factors. No dequantized base weight exists."""

    is_frozen_int8_linear = True

    def __init__(
        self,
        weight_q,
        weight_scale,
        bias=None,
        *,
        rank,
        alpha,
        seed,
        device="cpu",
        adapter_name="default",
        artifact_sha256=None,
        artifact_metadata=None,
    ):
        super().__init__()
        _validate_configuration(rank, alpha, adapter_name)
        frozen_int8._validate_payload(weight_q, weight_scale)
        if artifact_metadata is None:
            artifact_metadata = {}
        digest = frozen_int8.artifact_digest(weight_q, weight_scale, metadata=artifact_metadata)
        if artifact_sha256 is not None and artifact_sha256 != digest:
            raise ReferenceArithmeticError("Frozen int8 module bytes do not match the pinned artifact hash")
        if bias is not None and (
            not isinstance(bias, torch.Tensor) or bias.dtype != torch.float16 or bias.shape != (weight_q.shape[0],)
        ):
            raise ReferenceArithmeticError("Frozen int8 bias must be FP16 with one value per output")
        device = torch.device(device)
        self.in_features, self.out_features = int(weight_q.shape[1]), int(weight_q.shape[0])
        self.rank, self.alpha = rank, alpha
        self.scaling = float(alpha) / rank
        self.adapter_name = adapter_name
        self.artifact_sha256 = digest
        self.artifact_metadata = dict(artifact_metadata)
        self.register_buffer("weight_q", weight_q.detach().to(device=device, dtype=torch.int8).contiguous())
        self.register_buffer("weight_scale", weight_scale.detach().to(device=device, dtype=torch.float32).contiguous())
        if bias is None:
            self.bias = None
        else:
            self.register_buffer("bias", bias.detach().to(device=device, dtype=torch.float16).contiguous())
        self.lora_A = nn.ModuleDict()
        self.lora_B = nn.ModuleDict()
        self._artifact_cache = None
        # Initialize on CPU so the same seed produces the same adapter on every device and the caller's
        # random state is untouched. PEFT's default is Kaiming-uniform A and zero B.
        with torch.random.fork_rng(devices=[]):
            torch.manual_seed(seed)
            first = nn.Linear(self.in_features, rank, bias=False, dtype=torch.float32)
            nn.init.kaiming_uniform_(first.weight, a=math.sqrt(5))
            second = nn.Linear(rank, self.out_features, bias=False, dtype=torch.float32)
            nn.init.zeros_(second.weight)
        self.lora_A[adapter_name] = first.to(device=device, dtype=torch.float16)
        self.lora_B[adapter_name] = second.to(device=device, dtype=torch.float16)
        for parameter in (*self.lora_A.parameters(), *self.lora_B.parameters()):
            parameter.requires_grad_(True)

    def cpu_artifact(self):
        if self.weight_q.device.type != "cpu":
            raise ReferenceArithmeticError("The CPU oracle needs the frozen module on the host")
        key = (
            self.weight_q.data_ptr(),
            self.weight_scale.data_ptr(),
            self.weight_q._version,
            self.weight_scale._version,
            frozen_int8.metadata_digest(self.artifact_metadata),
        )
        if self._artifact_cache is not None and self._artifact_cache[0] == key:
            return self._artifact_cache[1]
        artifact = frozen_int8.FrozenInt8Artifact(
            weight_q=self.weight_q,
            weight_scale=self.weight_scale,
            metadata=self.artifact_metadata,
            sha256=self.artifact_sha256,
            format_version=frozen_int8.ARTIFACT_FORMAT_VERSION,
        )
        self._artifact_cache = (key, artifact)
        return artifact

    def base_linear_cpu(self, value):
        """Exact B22 int8 projection with the stored frozen bias, on the host."""
        return frozen_int8.linear(value, self.cpu_artifact(), self.bias)

    def lora_delta(self, value):
        """CPU strict adapter delta from the ORIGINAL activation.

        Both matrix products widen the FP16 factors and use the fixed adjacent-pair FP32 tree, the scale uses
        the strict multiply and nonfinite values are rejected. This is separate from the exact-integer base but
        is the same operator contract the CUDA graph implements for nonzero adapters.
        """
        if not isinstance(value, torch.Tensor) or not value.is_floating_point() or value.shape[-1] != self.in_features:
            raise ReferenceArithmeticError("A LoRA delta needs a floating tensor with the base input width")
        if value.device.type != "cpu" or self.weight_q.device.type != "cpu":
            raise ReferenceArithmeticError("The strict CPU adapter delta needs host storage")
        adapter_a = self.lora_A[self.adapter_name].weight
        adapter_b = self.lora_B[self.adapter_name].weight
        middle = ops.linear(value, adapter_a)
        delta = ops.linear(middle, adapter_b)
        return ops.mul(delta, self.scaling)

    def forward(self, value):
        """CPU oracle: exact frozen base, then the separately named adapter delta."""
        if not isinstance(value, torch.Tensor) or value.device.type != "cpu":
            raise ReferenceArithmeticError("FrozenInt8LoraLinear.forward is the CPU oracle; use the frozen backend")
        base = self.base_linear_cpu(value)
        return frozen_int8.combine_adapter(base, self.lora_delta(value))

    def extra_repr(self):
        return (
            f"in_features={self.in_features}, out_features={self.out_features}, rank={self.rank}, "
            f"alpha={self.alpha}, artifact_sha256={self.artifact_sha256}"
        )


def frozen_modules(model):
    """Yield ``(qualified_name, module)`` for every typed frozen projection."""
    for name, module in model.named_modules():
        if getattr(module, "is_frozen_int8_linear", False):
            yield name, module


def _check_source_linear(module):
    if (
        not isinstance(module, nn.Linear)
        or module.weight.dtype != torch.float16
        or module.weight.ndim != 2
        or module.weight.shape[0] < 1
        or not 1 <= module.weight.shape[1] <= frozen_int8.MAX_WIDTH
        or (
            module.bias is not None
            and (module.bias.dtype != torch.float16 or module.bias.shape != module.weight.shape[:1])
        )
    ):
        raise ReferenceArithmeticError("A frozen projection must start from a supported FP16 nn.Linear")
    return module


def _quantize_and_pin(module, name, metadata, artifact_path, expected_sha256):
    metadata = {} if metadata is None else dict(metadata)
    metadata.setdefault("module", name)
    source = module.weight.detach().to(device="cpu", dtype=torch.float32)
    if artifact_path is not None:
        artifact_path = Path(artifact_path)
        if artifact_path.exists():
            artifact = frozen_int8.read_artifact(artifact_path, expected_sha256=expected_sha256)
            if artifact.weight_q.shape != tuple(module.weight.shape):
                raise ReferenceArithmeticError("Pinned artifact shape does not match the target projection")
            weight_q, weight_scale = artifact.weight_q, artifact.weight_scale
            metadata = dict(artifact.metadata)
            digest = artifact.sha256
        else:
            weight_q, weight_scale = frozen_int8.quantize_weight(source)
            digest = frozen_int8.artifact_digest(weight_q, weight_scale, metadata=metadata)
            if expected_sha256 is not None and digest != expected_sha256:
                raise ReferenceArithmeticError("Freshly quantized bytes do not match the pinned artifact hash")
            artifact_path.parent.mkdir(parents=True, exist_ok=True)
            written = frozen_int8.write_artifact(artifact_path, weight_q, weight_scale, metadata=metadata)
            if written != digest:
                raise ReferenceArithmeticError("Artifact writer changed the content address")
    else:
        weight_q, weight_scale = frozen_int8.quantize_weight(source)
        digest = frozen_int8.artifact_digest(weight_q, weight_scale, metadata=metadata)
        if expected_sha256 is not None and digest != expected_sha256:
            raise ReferenceArithmeticError("Freshly quantized bytes do not match the pinned artifact hash")
    return weight_q, weight_scale, metadata, digest


def freeze_linear(
    module,
    *,
    rank,
    alpha,
    seed,
    name="projection",
    device=None,
    adapter_name="default",
    metadata=None,
    artifact_path=None,
    expected_sha256=None,
):
    """Replace one FP16 ``nn.Linear`` by typed frozen storage, optionally pinned to an artifact file.

    Without ``artifact_path`` the source weight is quantized on the host and the canonical bytes are content
    addressed in memory. With a path, an existing file is verified and used; a missing file is written only
    after the computed digest matches ``expected_sha256`` when one is supplied.
    """
    _check_source_linear(module)
    target_device = module.weight.device if device is None else torch.device(device)
    weight_q, weight_scale, metadata, digest = _quantize_and_pin(module, name, metadata, artifact_path, expected_sha256)
    result = FrozenInt8LoraLinear(
        weight_q,
        weight_scale,
        None if module.bias is None else module.bias.detach(),
        rank=rank,
        alpha=alpha,
        seed=seed,
        device=target_device,
        adapter_name=adapter_name,
        artifact_sha256=digest,
        artifact_metadata=metadata,
    )
    result.train(module.training)
    return result, digest


def _replace(parent, attribute, value):
    setattr(parent, attribute, value)


def _parent_of(model, qualified_name):
    if "." not in qualified_name:
        return model, qualified_name
    parent_name, attribute = qualified_name.rsplit(".", 1)
    return model.get_submodule(parent_name), attribute


def freeze_projections(
    model,
    *,
    rank,
    alpha,
    seed,
    target_modules=DEFAULT_TARGETS,
    artifact_directory=None,
    expected_sha256=None,
    metadata=None,
):
    """Replace every matching FP16 projection with typed frozen storage and return ``name -> digest``.

    ``target_modules`` uses the same suffix matching as the PEFT LoRA space. A possibly tied LM head is never
    targeted silently: quantizing it alone would break tied storage.
    """
    if not isinstance(target_modules, (list, tuple)) or not target_modules:
        raise ReferenceArithmeticError("Frozen projections need a nonempty target list")
    targets = tuple(target_modules)
    if not all(isinstance(target, str) and target for target in targets):
        raise ReferenceArithmeticError("Frozen projection targets must be nonempty strings")
    if expected_sha256 is not None and not isinstance(expected_sha256, dict):
        raise ReferenceArithmeticError("Pinned artifact hashes must be a name -> sha256 mapping")
    tied_head_weight = getattr(model.lm_head, "weight", None)
    tied_head = tied_head_weight is not None and tied_head_weight is model.model.embed_tokens.weight
    names = [
        name
        for name, module in model.named_modules()
        if isinstance(module, nn.Linear) and any(name == target or name.endswith("." + target) for target in targets)
    ]
    if not names:
        raise ReferenceArithmeticError("The frozen target list selects no projection")
    if tied_head and any(name.endswith("lm_head") for name in names):
        raise ReferenceArithmeticError("Cannot quantize a tied LM head without breaking tied storage")
    if artifact_directory is not None:
        artifact_directory = Path(artifact_directory)
        artifact_directory.mkdir(parents=True, exist_ok=True)
    digests = {}
    for name in names:
        module = model.get_submodule(name)
        path = None if artifact_directory is None else artifact_directory / f"{name.replace('.', '_')}.fint8"
        expected = None if expected_sha256 is None else expected_sha256.get(name)
        frozen, digest = freeze_linear(
            module,
            rank=rank,
            alpha=alpha,
            seed=_adapter_seed(seed, name),
            name=name,
            metadata=metadata,
            artifact_path=path,
            expected_sha256=expected,
        )
        parent, attribute = _parent_of(model, name)
        _replace(parent, attribute, frozen)
        digests[name] = digest
    return digests


def freeze_tied_head(model, *, metadata=None, artifact_path=None, expected_sha256=None):
    """Attach pinned int8 storage to a tied LM head without replacing the shared FP16 embedding weight.

    The head has no ``weight`` parameter of its own after this call either: the original FP16 parameter stays
    tied to ``embed_tokens`` and the frozen rows/scales live in sidecar buffers. Decoding through the frozen
    backend selects those buffers, so the head arithmetic is the pinned int8 product rather than the strict
    FP16 product. Replacing the module instead would break the tie, which is why this is a separate explicit
    operation from :func:`freeze_projections`.
    """
    head = getattr(model, "lm_head", None)
    embeddings = getattr(getattr(model, "model", None), "embed_tokens", None)
    if (
        not isinstance(head, nn.Linear)
        or not isinstance(embeddings, nn.Embedding)
        or head.weight is not embeddings.weight
    ):
        raise ReferenceArithmeticError("A frozen sidecar head requires the tied FP16 LM head")
    if getattr(head, "is_frozen_int8_head", False) or hasattr(head, "frozen_weight_q"):
        raise ReferenceArithmeticError("The LM head already carries frozen int8 storage")
    _check_source_linear(head)
    weight_q, weight_scale, metadata, digest = _quantize_and_pin(
        head, "lm_head", metadata, artifact_path, expected_sha256
    )
    device = head.weight.device
    head.is_frozen_int8_head = True
    head.frozen_head_sha256 = digest
    head.frozen_head_metadata = dict(metadata)
    head.register_buffer("frozen_weight_q", weight_q.to(device=device, dtype=torch.int8).contiguous())
    head.register_buffer("frozen_weight_scale", weight_scale.to(device=device, dtype=torch.float32).contiguous())
    return digest


def require_frozen_projections(model, names):
    """Fail unless exactly the named modules are typed frozen projections."""
    found = dict(frozen_modules(model))
    if set(found) != set(names):
        raise ReferenceArithmeticError("Frozen projection set does not match the admitted graph")
    for name, module in found.items():
        if module.training or module.weight_q.dtype != torch.int8 or module.weight_scale.dtype != torch.float32:
            raise ReferenceArithmeticError(f"Frozen projection {name} has invalid typed storage")
    return found


def create_initial_frozen_adapter(model, path):
    """Write the current (deterministic) adapters and return the file SHA-256."""
    return write_weights(model, trainable_schema(model), path)


def load_frozen_adapter_(model, path, expected_sha256):
    """Load a pinned adapter file into the frozen model's trainable schema."""
    load_adapter_(model, path, expected_sha256)


def frozen_identity():
    return {
        "storage": FROZEN_LORA_VERSION,
        "artifact": frozen_int8.identity(),
        "adapterArithmetic": frozen_int8.ADAPTER_ARITHMETIC_VERSION,
        "baseDtype": "int8-per-output-row",
        "biasDtype": "float16",
        "trainable": "lora_A/lora_B only",
        "hardwareQualified": False,
    }
