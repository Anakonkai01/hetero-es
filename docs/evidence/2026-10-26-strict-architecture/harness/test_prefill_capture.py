import copy
import os

import pytest
import torch

from heteroes.eval.integer_decoder import IntegerDecoderReference
from prefill_capture import PrefillIntegerGraph
from test_strict_decoder import model_for


@pytest.mark.skipif(os.environ.get('HETEROES_GPU_ACCEPTANCE')!='1' or not torch.cuda.is_available(),reason='GPU opt-in')
@pytest.mark.parametrize('family',['qwen2','llama'])
def test_prefill_capture_replays_live_inputs_and_weights_then_clears_request_buffers(family):
    cpu=model_for(family)
    model=copy.deepcopy(cpu).cuda()
    oracle=IntegerDecoderReference(cpu,magnitude_bits=22,max_context=32,allow_fixture=True)
    engine=PrefillIntegerGraph(model,magnitude_bits=22,max_context=32,allow_fixture=True)
    ids=torch.tensor([[0,3,5],[7,11,13]],device='cuda')
    mask=ids!=0
    parent=cpu.model.layers[0].self_attn.q_proj.weight.detach().clone()
    count=None
    for factor,change_input in ((1.,False),(1.,True),(-16.,False),(1.,False)):
        with torch.no_grad():
            cpu.model.layers[0].self_attn.q_proj.weight.copy_(parent*factor)
            model.model.layers[0].self_attn.q_proj.weight.copy_((parent*factor).cuda())
        current=ids.clone()
        if change_input:current[mask]+=1
        expected=oracle.generate(current.cpu(),attention_mask=mask.cpu(),max_new_tokens=4,eos_token_id=[])
        actual=engine.generate(current,attention_mask=mask,max_new_tokens=4,eos_token_id=[])
        assert torch.equal(actual.cpu(),expected)
        assert all(not bool(t.any())for t in engine.prefill_request_buffers())
        if count is None:count=engine.prefill_capture_count
        else:assert engine.prefill_capture_count==count
    assert count==1
    engine.release_graph()
    assert engine._prefill_graph is None and not engine.prefill_request_buffers()
