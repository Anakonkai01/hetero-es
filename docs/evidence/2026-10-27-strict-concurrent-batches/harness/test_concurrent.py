"""Concurrent graph owners must preserve ordering, live weight reads and exact restore across requests."""
import torch
from heteroes.eval.integer_decoder import IntegerDecoderGraph,IntegerDecoderReference
from test_strict_decoder import model_for
from concurrent_batches import ConcurrentRequests

def factory(engine,tokens):
    def run(rows):
        width=max(map(len,rows));ids=torch.zeros(len(rows),width,dtype=torch.long,device=engine.device)
        mask=torch.zeros_like(ids)
        for i,r in enumerate(rows):ids[i,-len(r):]=torch.tensor(r,device=engine.device);mask[i,-len(r):]=1
        out=engine.generate(ids,attention_mask=mask,max_new_tokens=tokens,eos_token_id=[],repetition_penalty=1.)
        return out[:,width:].tolist()
    return run

def test_concurrent_live_model_and_restore_match_independent_cpu_decoder():
    cpu=model_for('llama');model=model_for('llama').cuda()
    oracle=IntegerDecoderReference(cpu,allow_fixture=True,max_context=32,magnitude_bits=22)
    engines=[IntegerDecoderGraph(model,allow_fixture=True,max_context=32,magnitude_bits=22) for _ in range(2)]
    scheduler=ConcurrentRequests(engines,factory)
    rows=[[3,5,7],[9],[11,13],[17,19]]
    saved=cpu.model.layers[0].mlp.down_proj.weight.detach().clone()
    try:
        for factor in (1.,-16.,1.):
            with torch.no_grad():
                cpu.model.layers[0].mlp.down_proj.weight.copy_(saved*factor)
                model.model.layers[0].mlp.down_proj.weight.copy_((saved*factor).cuda())
            expected=factory(oracle,3)(rows)
            assert scheduler.run(rows,3)==expected
    finally:scheduler.close()
