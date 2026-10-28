import copy
import os
import pytest
import torch
from test_strict_decoder import model_for
from heteroes.eval.integer_decoder import IntegerDecoderReference
from heteroes.eval.reference_ops import ReferenceArithmeticError

pytestmark=pytest.mark.skipif(os.environ.get('HETEROES_GPU_ACCEPTANCE')!='1' or not torch.cuda.is_available(),reason='GPU opt-in')

@pytest.mark.parametrize('family',['qwen2','llama-wide'])
def test_proposal_contents_do_not_change_cpu_tokens_across_candidate_change_restore_and_eos(family):
    from speculative import SpeculativeGraph
    cpu=model_for(family);model=copy.deepcopy(cpu).cuda()
    engine=SpeculativeGraph(model,allow_fixture=True,max_context=32,block=4,max_graph_bytes=1024**3)
    oracle=IntegerDecoderReference(cpu,allow_fixture=True,max_context=32)
    ids=torch.tensor([[0,3,5],[7,11,13]]);mask=ids!=0
    parent=cpu.model.layers[0].mlp.down_proj.weight.detach().clone();saved=[]
    for factor in (1.,-16.,1.):
        with torch.no_grad():
            cpu.model.layers[0].mlp.down_proj.weight.copy_(parent*factor)
            model.model.layers[0].mlp.down_proj.weight.copy_((parent*factor).cuda())
        expected=oracle.generate(ids,attention_mask=mask,max_new_tokens=7,eos_token_id=[],repetition_penalty=1.)
        completion=expected[:,ids.shape[1]:].tolist()
        def perfect(owner,outputs,count):return completion[owner][len(outputs):len(outputs)+count]
        def wrong(owner,outputs,count):return [(completion[owner][len(outputs)]+1)%43]*count
        for proposer in (None,perfect,wrong):
            actual=engine.generate(ids.cuda(),attention_mask=mask.cuda(),max_new_tokens=7,
                                   eos_token_id=[],repetition_penalty=1.,proposer=proposer)
            assert torch.equal(actual.cpu(),expected)
            if proposer is perfect:assert engine.stats['acceptedDraftTokens']>0
            if proposer is wrong:assert engine.stats['acceptedDraftTokens']==0
            assert all(not bool(t.any())for t in engine._session.caches)
            assert all(not bool(t.any())for t in engine.request_buffers())
        saved.append(actual.cpu())
        eos=completion[0][2]
        expected_eos=oracle.generate(ids,attention_mask=mask,max_new_tokens=7,eos_token_id=[eos],repetition_penalty=1.)
        actual=engine.generate(ids.cuda(),attention_mask=mask.cuda(),max_new_tokens=7,
                               eos_token_id=[eos],repetition_penalty=1.,proposer=perfect)
        assert torch.equal(actual.cpu(),expected_eos)
    assert torch.equal(saved[0],saved[2])
    engine.release_graph()

def test_context_tail_invalid_proposals_failure_cleanup_and_recapture():
    from speculative import SpeculativeGraph
    cpu=model_for('llama');model=copy.deepcopy(cpu).cuda()
    engine=SpeculativeGraph(model,allow_fixture=True,max_context=8,block=4,max_graph_bytes=1024**3)
    ids=torch.tensor([[3,5]])
    oracle=IntegerDecoderReference(cpu,allow_fixture=True,max_context=8)
    expected=oracle.generate(ids,max_new_tokens=6,eos_token_id=[])
    tokens=expected[:,2:].tolist()
    actual=engine.generate(ids.cuda(),max_new_tokens=6,eos_token_id=[],
                           proposer=lambda owner,output,n:tokens[owner][len(output):len(output)+n])
    assert torch.equal(actual.cpu(),expected)
    with pytest.raises(ReferenceArithmeticError,match='proposal'):
        engine.generate(ids.cuda(),max_new_tokens=6,eos_token_id=[],proposer=lambda *args:[999])
    assert not engine._call_lock.locked() and not engine.kernels._request_active
    assert all(not bool(t.any())for t in engine.request_buffers())
    assert torch.equal(engine.generate(ids.cuda(),max_new_tokens=6,eos_token_id=[]).cpu(),expected)
    engine.release_graph()

def test_invalid_unaccepted_speculation_falls_back_to_finite_true_path():
    from speculative import SpeculativeGraph
    cpu=model_for('llama')
    with torch.no_grad():
        for parameter in cpu.parameters():parameter.zero_()
        cpu.model.embed_tokens.weight[1].fill_(1.)
        for layer in cpu.model.layers:
            layer.input_layernorm.weight.fill_(1.)
            layer.post_attention_layernorm.weight.fill_(1.)
        cpu.model.norm.weight.fill_(1.)
        for name in ('gate_proj','up_proj','down_proj'):getattr(cpu.model.layers[0].mlp,name).weight.fill_(65504.)
    model=copy.deepcopy(cpu).cuda()
    engine=SpeculativeGraph(model,allow_fixture=True,max_context=32,block=4,max_graph_bytes=1024**3)
    ids=torch.tensor([[0,0]],device='cuda')
    expected=IntegerDecoderReference(cpu,allow_fixture=True,max_context=32).generate(ids.cpu(),max_new_tokens=5,eos_token_id=[])
    actual=engine.generate(ids,max_new_tokens=5,eos_token_id=[],proposer=lambda owner,out,n:[1]*n)
    assert torch.equal(actual.cpu(),expected) and actual[:,2:].eq(0).all()
    assert engine.stats['numericFallbacks']>0
    assert all(not bool(t.any())for t in engine._session.caches)
    engine.release_graph()

def test_eos_inside_accepted_block_stops_before_bonus_with_an_already_finished_owner():
    from speculative import SpeculativeGraph
    cpu=model_for('llama')
    with torch.no_grad():
        for parameter in cpu.parameters():parameter.zero_()
        for token in range(12):
            cpu.model.embed_tokens.weight[token,token]=1.
            cpu.lm_head.weight[token+1,token]=1.
        for layer in cpu.model.layers:
            layer.input_layernorm.weight.fill_(1.)
            layer.post_attention_layernorm.weight.fill_(1.)
        cpu.model.norm.weight.fill_(1.)
    model=copy.deepcopy(cpu).cuda()
    engine=SpeculativeGraph(model,allow_fixture=True,max_context=32,block=4,max_graph_bytes=1024**3)
    ids=torch.tensor([[0,1,2,3],[0,1,2,5]])
    oracle=IntegerDecoderReference(cpu,allow_fixture=True,max_context=32)
    expected=oracle.generate(ids,max_new_tokens=7,eos_token_id=[6])
    targets=expected[:,4:].tolist()
    actual=engine.generate(ids.cuda(),max_new_tokens=7,eos_token_id=[6],
                           proposer=lambda owner,out,n:targets[owner][len(out):len(out)+n])
    assert actual.cpu().tolist()==expected.tolist()==[[0,1,2,3,4,5,6],[0,1,2,5,6,0,0]]
    assert engine.stats['acceptedDraftTokens']==2
    assert engine.stats['dummyPrefixRows']>0
    repeated=engine.generate(ids.cuda(),max_new_tokens=7,eos_token_id=[6],
                             proposer=lambda owner,out,n:targets[owner][len(out):len(out)+n])
    assert torch.equal(repeated,actual) and engine.stats['captures']==0
    engine.release_graph()

def test_replacement_parameter_and_foreign_stream_force_fresh_capture():
    from speculative import SpeculativeGraph
    cpu=model_for('llama-wide');model=copy.deepcopy(cpu).cuda()
    engine=SpeculativeGraph(model,allow_fixture=True,max_context=32,block=2,max_graph_bytes=1024**3)
    oracle=IntegerDecoderReference(cpu,allow_fixture=True,max_context=32)
    ids=torch.tensor([[3,5,7]],device='cuda');torch.cuda.synchronize()
    assert torch.equal(engine.generate(ids,max_new_tokens=4,eos_token_id=[]).cpu(),
                       oracle.generate(ids.cpu(),max_new_tokens=4,eos_token_id=[]))
    previous=engine._session
    with torch.no_grad():cpu.lm_head.weight.mul_(-16.)
    model.lm_head.weight=torch.nn.Parameter(cpu.lm_head.weight.detach().clone().cuda())
    torch.cuda.synchronize()
    stream=torch.cuda.Stream()
    with torch.cuda.stream(stream):
        actual=engine.generate(ids,max_new_tokens=4,eos_token_id=[])
        assert torch.equal(actual.cpu(),oracle.generate(ids.cpu(),max_new_tokens=4,eos_token_id=[]))
    assert engine._session is not previous and previous.closed
    assert all(not bool(t.any())for t in engine.request_buffers())
    engine.release_graph()
