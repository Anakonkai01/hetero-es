"""Unselected contiguous live projection groups; exact integer kernels only."""
import hashlib
from pathlib import Path

from heteroes.canonical import canonical_json_hash
from heteroes.eval.integer_decoder import IntegerDecoderGraph
from heteroes.eval.fp16_decoder import Fp16DecoderGraph


class MergedIntegerGraph(IntegerDecoderGraph):
    # Reuse only the already tested storage/alias guards, never the vendor projection methods.
    _merge = Fp16DecoderGraph._merge
    _group_signature = staticmethod(Fp16DecoderGraph._group_signature)
    _merged_group = Fp16DecoderGraph._merged_group

    def __init__(self, model, **kwargs):
        self._merged = {}
        self._merged_signatures = {}
        super().__init__(model, **kwargs)
        self._groups = []
        for layer in model.model.layers:
            self._groups += [(layer.self_attn.q_proj, layer.self_attn.k_proj, layer.self_attn.v_proj),
                             (layer.mlp.gate_proj, layer.mlp.up_proj)]
        for modules in self._groups:
            self._merge(modules)
        self.identity = {**self.identity, 'projectionGrouping': 'live_contiguous_integer_probe',
                         'groupingSourceSha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
        self.fingerprint = canonical_json_hash(self.identity)

    def _projection_weights(self):
        for modules in self._groups:
            merged = self._merged_group(modules)
            if merged is None:
                yield from (module.weight for module in modules)
            else:
                yield merged[0]
        for layer in self.model.model.layers:
            yield layer.self_attn.o_proj.weight
            yield layer.mlp.down_proj.weight
        yield self.model.lm_head.weight

    def _project_many(self, value, modules, flag):
        merged = self._merged_group(modules)
        if merged is None:
            return super()._project_many(value, modules, flag)
        weight, bias, outputs = merged
        combined = self.kernels.linear(value, weight, bias, error_flag=flag)
        return tuple(part.contiguous() for part in combined.split(outputs, dim=-1))

    def _decode_project_many(self, value, modules, flag):
        merged = self._merged_group(modules)
        if merged is None:
            return super()._decode_project_many(value, modules, flag)
        weight, bias, outputs = merged
        combined = self.kernels.linear_decode(value, weight, bias, error_flag=flag,
                                              target_ctas_per_sm=self._decode_target)
        return tuple(part.contiguous() for part in combined.split(outputs, dim=-1))
