"""The fused operator must survive graph replay, live weight changes, restore and shrinking EOS owners."""
import torch
from transformers import Qwen2Config,Qwen2ForCausalLM
from heteroes.eval.integer_decoder import IntegerDecoderGraph
from graph import FusionGraph

def test_fused_graph_keeps_tokens_logits_restore_and_eos():
    torch.manual_seed(387)
    config=Qwen2Config(hidden_size=896,intermediate_size=128,num_attention_heads=14,num_key_value_heads=2,
                      num_hidden_layers=1,vocab_size=131,max_position_embeddings=64,eos_token_id=130,pad_token_id=0,tie_word_embeddings=False)
    config._attn_implementation='eager'
    model=Qwen2ForCausalLM(config).half().cuda().eval()
    base=IntegerDecoderGraph(model,allow_fixture=True,max_context=32,magnitude_bits=22)
    fast=FusionGraph(model,allow_fixture=True,max_context=32,magnitude_bits=22)
    ids=torch.tensor([[3,5,7],[11,13,17],[19,23,29]],device='cuda')
    snapshot=model.model.layers[0].self_attn.q_proj.weight.detach().clone()
    for factor in (1.,-2.,1.):
        with torch.no_grad():model.model.layers[0].self_attn.q_proj.weight.copy_(snapshot*factor)
        a=base.generate(ids,max_new_tokens=3,eos_token_id=[]);b=fast.generate(ids,max_new_tokens=3,eos_token_id=[])
        assert torch.equal(a,b)
        assert torch.equal(base._session.last_logits.view(torch.int32),fast._session.last_logits.view(torch.int32))
    assert fast._session.capture_count==1
    eos=int(a[0,ids.shape[1]])
    a=base.generate(ids,max_new_tokens=4,eos_token_id=[eos]);b=fast.generate(ids,max_new_tokens=4,eos_token_id=[eos])
    assert torch.equal(a,b)
