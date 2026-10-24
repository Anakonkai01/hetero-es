"""Pinned-Qwen compatibility wrapper for the shared strict CUDA decoder graph (experimental)."""

import hashlib
from pathlib import Path

from heteroes.canonical import canonical_json_hash
from heteroes.eval import strict_cuda
from heteroes.eval.qwen2_reference import Qwen2Reference
from heteroes.eval.reference_ops import ReferenceArithmeticError
from heteroes.eval.strict_decoder import CudaDecoderMixin, require_cuda

STRICT_CUDA_BACKEND = "qwen2_pairwise_f32_cuda_v2_experimental"


class Qwen2StrictCuda(CudaDecoderMixin, Qwen2Reference):
    def __init__(self, model, *, max_context=256, allow_fixture=False):
        require_cuda(model)
        super().__init__(model, max_context=max_context, allow_fixture=allow_fixture)
        if max_context > strict_cuda.MAX_ATTENTION_KEYS:
            raise ReferenceArithmeticError("Strict CUDA attention context limit exceeded")
        self._initialize_cuda_graph(STRICT_CUDA_BACKEND)
        self.identity["wrapperSourceSha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        self.fingerprint = canonical_json_hash(self.identity)
