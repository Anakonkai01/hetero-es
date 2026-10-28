import copy
import os

import pytest
import torch

from heteroes.eval.integer_decoder import IntegerDecoderReference
from heteroes.eval.candidate import model_weights_sha256
from heteroes.model.schema import build_parameter_schema
from merged_integer import MergedIntegerGraph
from test_strict_decoder import model_for


@pytest.mark.skipif(os.environ.get('HETEROES_GPU_ACCEPTANCE') != '1' or not torch.cuda.is_available(), reason='GPU opt-in')
@pytest.mark.parametrize('bits', [14, 22])
def test_live_grouped_projection_matches_independent_oracle_through_change_restore(bits):
    cpu = model_for('qwen2')
    model = copy.deepcopy(cpu).cuda()
    schema = build_parameter_schema(model)
    parameter_ids = [id(p) for p in model.parameters()]
    parent_hash = model_weights_sha256(model, schema)
    oracle = IntegerDecoderReference(cpu, magnitude_bits=bits, max_context=32, allow_fixture=True)
    engine = MergedIntegerGraph(model, magnitude_bits=bits, max_context=32, allow_fixture=True)
    assert build_parameter_schema(model).hash == schema.hash
    assert [id(p) for p in model.parameters()] == parameter_ids
    assert model_weights_sha256(model, schema) == parent_hash
    original = cpu.model.layers[0].self_attn.q_proj.weight.detach().clone()
    ids = torch.tensor([[0, 3, 5], [7, 11, 13]], device='cuda')
    mask = ids != 0
    first = None
    for factor in (1.0, -16.0, 1.0):
        with torch.no_grad():
            cpu.model.layers[0].self_attn.q_proj.weight.copy_(original * factor)
            model.model.layers[0].self_attn.q_proj.weight.copy_((original * factor).cuda())
        expected = oracle.generate(ids.cpu(), attention_mask=mask.cpu(), max_new_tokens=4, eos_token_id=[])
        actual = engine.generate(ids, attention_mask=mask, max_new_tokens=4, eos_token_id=[])
        assert torch.equal(actual.cpu(), expected)
        rows = [ids[i:i+1, mask[i]] for i in range(2)]
        logits, _ = engine.forward_batch(rows)
        reference = torch.cat([oracle.forward_tokens(row.cpu())[0] for row in rows])
        assert torch.equal(logits.cpu().view(torch.int32), reference.view(torch.int32))
        if first is None:
            first = logits.cpu().clone()
        elif factor == 1.0:
            assert torch.equal(first.view(torch.int32), logits.cpu().view(torch.int32))
    assert model_weights_sha256(model, schema) == parent_hash
