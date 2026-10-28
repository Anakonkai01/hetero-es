import copy
import os

import pytest
import torch

from bounded_decoder import BoundedDecoderReference, BoundedDecoderGraph
from test_strict_decoder import model_for


@pytest.mark.skipif(os.environ.get('HETEROES_GPU_ACCEPTANCE') != '1' or not torch.cuda.is_available(), reason='GPU opt-in')
@pytest.mark.parametrize('family',['qwen2','llama'])
def test_new_arithmetic_decoder_matches_independent_cpu_through_live_change_and_restore(family):
    cpu = model_for(family)
    model = copy.deepcopy(cpu).cuda()
    oracle = BoundedDecoderReference(cpu,activation_bits=8,weight_bits=8,max_context=32,allow_fixture=True)
    engine = BoundedDecoderGraph(model,activation_bits=8,weight_bits=8,max_context=32,allow_fixture=True)
    ids = torch.tensor([[0,3,5],[7,11,13]],device='cuda')
    mask = ids!=0
    parent = cpu.model.layers[0].self_attn.q_proj.weight.detach().clone()
    original = None
    for factor in (1.,-16.,1.):
        with torch.no_grad():
            cpu.model.layers[0].self_attn.q_proj.weight.copy_(parent*factor)
            model.model.layers[0].self_attn.q_proj.weight.copy_((parent*factor).cuda())
        expected = oracle.generate(ids.cpu(),attention_mask=mask.cpu(),max_new_tokens=4,eos_token_id=[])
        actual = engine.generate(ids,attention_mask=mask,max_new_tokens=4,eos_token_id=[])
        assert torch.equal(actual.cpu(),expected)
        rows = [ids[i:i+1,mask[i]]for i in range(2)]
        logits,_ = engine.forward_batch(rows)
        expected_logits = torch.cat([oracle.forward_tokens(row.cpu())[0]for row in rows])
        assert torch.equal(logits.cpu().view(torch.int32),expected_logits.view(torch.int32))
        if original is None:original=logits.cpu().clone()
        elif factor==1.:assert torch.equal(logits.cpu().view(torch.int32),original.view(torch.int32))
    assert engine.identity['operators']['linear']['operator']=='bounded_half_integer_dot_v1_probe'
