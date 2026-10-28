import pytest
from heteroes.eval import integer_plan as p

@pytest.mark.parametrize('width,outputs,split',[(896,1152,5),(4864,896,7),(896,896,7),(896,9728,2),(896,151936,1)])
def test_balanced_wave_plan(width,outputs,split):
    plan=p.decode_linear_plan(width,32,outputs,70,resident_ctas_per_sm=3)
    assert plan.split_k==split
    assert plan.partial_bytes==(0 if split==1 else split*32*outputs*8)

def test_limits_and_old_row_tile_still_apply():
    assert p.decode_linear_plan(896,32,1152,70,resident_ctas_per_sm=3,max_partial_bytes=600000).split_k==2
    assert p.decode_linear_plan(896,32,1152,70,resident_ctas_per_sm=3,max_partial_bytes=1).split_k==1
    for rows in (1,8,16):
        assert p.decode_linear_plan(896,rows,1152,70,resident_ctas_per_sm=3)==p.decode_linear_plan(896,rows,1152,70)
    assert p.decode_linear_plan(896,32,1152,70,resident_ctas_per_sm=3,target_ctas_per_sm=0).split_k==1

def test_bound_covers_every_active_batch_and_repeated_projection():
    shapes=[(896,1152),(4864,896),(896,896),(896,9728),(4864,896)]
    expected=sum(max(p.decode_linear_plan(w,r,n,70,resident_ctas_per_sm=3).partial_bytes for r in range(1,33)) for w,n in shapes)
    assert p.decode_workspace_bound(shapes,32,70,resident_ctas_per_sm=3)==expected
