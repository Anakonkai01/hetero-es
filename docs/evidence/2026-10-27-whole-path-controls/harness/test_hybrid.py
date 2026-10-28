import copy
import os
import pytest
import torch
from hybrid_precision import MixedDecoderGraph,MixedDecoderReference
from test_strict_decoder import model_for

gpu=pytest.mark.skipif(os.environ.get('HETEROES_GPU_ACCEPTANCE')!='1' or not torch.cuda.is_available(),reason='GPU opt-in')
@gpu
@pytest.mark.parametrize('family',['llama','qwen2','mistral'])
def test_mixed_graph_equals_independent_reference_cached_uncached_and_rebound(family):
 cpu=model_for(family);model=copy.deepcopy(cpu).cuda()
 ref=MixedDecoderReference(cpu,max_context=32,allow_fixture=True)
 graph=MixedDecoderGraph(model,max_context=32,allow_fixture=True)
 ids=torch.tensor([[3,5,7],[11,13,17]],device='cuda')
 for factor in (1,-4,1):
  saved=cpu.model.layers[0].mlp.down_proj.weight.detach().clone()
  with torch.no_grad():
   cpu.model.layers[0].mlp.down_proj.weight.mul_(factor)
   model.model.layers[0].mlp.down_proj.weight.copy_(cpu.model.layers[0].mlp.down_proj.weight.cuda())
  expected=ref.generate(ids.cpu(),max_new_tokens=4,eos_token_id=[])
  assert torch.equal(graph.generate(ids,max_new_tokens=4,eos_token_id=[]).cpu(),expected)
  assert torch.equal(graph.generate(ids,max_new_tokens=4,eos_token_id=[],use_cache=False).cpu(),expected)
  assert all(not bool(t.any()) for t in graph._mlp_kernels.weight_metadata_buffers())
  with torch.no_grad():
   cpu.model.layers[0].mlp.down_proj.weight.copy_(saved);model.model.layers[0].mlp.down_proj.weight.copy_(saved.cuda())
 graph.release_graph()
