"""Graph-composition probe for exact QKV-finish/RoPE/cache-store/attention fusion."""
import hashlib
import inspect
from pathlib import Path
import textwrap
from heteroes.canonical import canonical_json_hash
from heteroes.eval import strict_decoder_graph as sdg,strict_cuda as sc
from heteroes.eval.integer_decoder import IntegerDecoderGraph
from fusion import FusedKernels

CORE=textwrap.dedent(inspect.getsource(sdg.StrictDecoderGraph._decode_core))
OLD='''        q = self._decode_attention_input(hidden, layer, epsilon, cosine, sine, state, keys, values, flag)
        mixed = kernels.attention_packed(
            q, keys, values, layout, heads // kv_heads, float(self._attention_scale), error_flag=flag
        )'''
assert CORE.count(OLD)==1
CORE=CORE.replace(OLD,'        mixed = self._decode_qkv_attention(hidden, layer, epsilon, cosine, sine, state, keys, values, layout, flag)')
scope=dict(vars(sdg));exec(CORE,scope)

class FusionGraph(IntegerDecoderGraph):
    _decode_core=scope['_decode_core']
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs);self.kernels.__class__=FusedKernels
        self.identity={**self.identity,'decodeQkvFinishAttention':'single_cta_owner_v1_probe',
                       'fusionSourceSha256':hashlib.sha256(Path(__file__).with_name('fusion.py').read_bytes()).hexdigest(),
                       'fusionGraphSha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
        self.fingerprint=canonical_json_hash(self.identity)
    def _decode_qkv_attention(self,hidden,layer,epsilon,cosine,sine,state,keys,values,layout,flag):
        c=self.config;k=self.kernels;repeats=c.num_attention_heads//c.num_key_value_heads
        if hidden.shape[0]>1 and self.head_dim==64 and 2<=repeats<=8 and k.arch=='sm_120' and k.magnitude_bits==22 and self._decode_target==8:
            attention=layer.self_attn
            modules=(attention.q_proj,attention.k_proj,attention.v_proj)
            weights=tuple(m.weight for m in modules);biases=tuple(getattr(m,'bias',None) for m in modules)
            prepared=k.rms_norm_quantized(hidden,layer.input_layernorm.weight,epsilon,error_flag=flag)
            result=k.qkv_attention(prepared,weights,biases,cosine,sine,c.num_attention_heads,c.num_key_value_heads,
                                   state.ranges,keys,values,float(self._attention_scale),max_keys=state.context,
                                   error_flag=flag,decode_target_ctas_per_sm=self._decode_target)
            if result is not None:return result
        q=self._decode_attention_input(hidden,layer,epsilon,cosine,sine,state,keys,values,flag)
        return k.attention_packed(q,keys,values,layout,repeats,float(self._attention_scale),error_flag=flag)
