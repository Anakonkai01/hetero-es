"""A smaller physical cache must preserve admitted inputs, output bits, restore and request clearing."""
import pytest
import torch
from test_strict_decoder import model_for
from heteroes.eval.integer_decoder import IntegerDecoderReference
from heteroes.eval.reference_ops import ReferenceArithmeticError
from bucket import BucketGraph

def test_cache_context_changes_keep_cpu_logits_tokens_restore_and_clearing():
    cpu=model_for('llama');model=model_for('llama').cuda()
    oracle=IntegerDecoderReference(cpu,allow_fixture=True,max_context=64,magnitude_bits=22)
    engine=BucketGraph(model,allow_fixture=True,max_context=64,magnitude_bits=22)
    saved=cpu.model.layers[0].mlp.down_proj.weight.detach().clone()
    small=torch.tensor([[3,5,7],[11,13,17]])
    large=torch.tensor([[3,5,7]*5+[11,13],[17,19,23]*5+[29,31]])
    for ids,factor,context in ((small,1.,16),(large,-16.,32),(small,1.,16)):
        with torch.no_grad():
            cpu.model.layers[0].mlp.down_proj.weight.copy_(saved*factor)
            model.model.layers[0].mlp.down_proj.weight.copy_((saved*factor).cuda())
        expected=oracle.generate(ids,max_new_tokens=3,eos_token_id=[])
        actual=engine.generate(ids.cuda(),max_new_tokens=3,eos_token_id=[])
        assert torch.equal(actual.cpu(),expected)
        logits,_=oracle.forward_tokens(expected[0,:-1][None])
        assert torch.equal(engine._session.last_logits[0].cpu().view(torch.int32),logits[0].view(torch.int32))
        assert engine.max_context==64 and engine._session.context==context
        assert all(t.shape[1]==2*context and not bool(t.any()) for t in engine._session.caches)
    state=engine._session
    engine.generate(small.cuda(),max_new_tokens=3,eos_token_id=[])
    assert engine._session is state and state.capture_count==1

def test_configured_context_and_original_conservative_budget_still_reject():
    model=model_for('llama').cuda()
    engine=BucketGraph(model,allow_fixture=True,max_context=64,magnitude_bits=22,max_graph_bytes=1)
    ids=torch.tensor([[3,5,7],[11,13,17]],device='cuda')
    with pytest.raises(ReferenceArithmeticError,match='memory budget'):engine.generate(ids,max_new_tokens=3,eos_token_id=[])
    assert engine._session is None
    with pytest.raises(ReferenceArithmeticError,match='context limit'):engine.generate(ids,max_new_tokens=64,eos_token_id=[])
