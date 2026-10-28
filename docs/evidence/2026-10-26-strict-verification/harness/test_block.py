import copy
import os
import pytest
import torch
from test_strict_decoder import model_for
from heteroes.eval.integer_decoder import IntegerDecoderGraph,IntegerDecoderReference

pytestmark=pytest.mark.skipif(os.environ.get('HETEROES_GPU_ACCEPTANCE')!='1' or not torch.cuda.is_available(),reason='GPU opt-in')

@pytest.mark.parametrize('family',['qwen2','llama-wide'])
def test_block_scores_every_hypothetical_prefix_and_replays_changed_guesses_and_weights(family):
    from block_verifier import BlockVerifier
    cpu=model_for(family);model=copy.deepcopy(cpu).cuda()
    engine=IntegerDecoderGraph(model,allow_fixture=True,max_context=32,max_graph_bytes=1024**3)
    oracle=IntegerDecoderReference(cpu,allow_fixture=True,max_context=32)
    prompts=[torch.tensor([[3,5]]),torch.tensor([[7,11,13]])]
    parent=cpu.model.layers[0].mlp.down_proj.weight.detach().clone()
    saved=[]
    for factor in (1.,-16.,1.):
        with torch.no_grad():
            cpu.model.layers[0].mlp.down_proj.weight.copy_(parent*factor)
            model.model.layers[0].mlp.down_proj.weight.copy_((parent*factor).cuda())
        with BlockVerifier(engine,[p.cuda()for p in prompts],4)as verifier:
            for guesses in (torch.tensor([[2,3,5,7],[11,13,17,19]]),torch.tensor([[19,17,13,11],[7,5,3,2]])):
                logits,chosen=verifier.run(guesses.cuda())
                expected=[]
                for row,prompt in enumerate(prompts):
                    for step in range(4):
                        sequence=torch.cat((prompt,guesses[row:row+1,:step+1]),dim=1)
                        expected.append(oracle.forward_tokens(sequence)[0])
                expected=torch.cat(expected)
                assert torch.equal(logits.cpu().view(torch.int32),expected.view(torch.int32))
                assert chosen.cpu().tolist()==expected.argmax(-1).reshape(2,4).tolist()
                saved.append(chosen.cpu().clone())
        assert all(not bool(t.any())for t in engine._session.caches)
    assert torch.equal(saved[0],saved[4])and torch.equal(saved[1],saved[5])
    engine.release_graph()
