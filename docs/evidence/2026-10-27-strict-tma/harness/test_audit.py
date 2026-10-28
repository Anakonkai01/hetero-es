"""The narrow memory-fence opcode extension must not admit floating arithmetic or unknown variants."""
from heteroes.eval.strict_cuda import audit_sass

def test_tma_memory_fence_is_explicit_and_other_forbidden_operations_stay_rejected():
    source='FENCE.VIEW.ASYNC.S ;\nFFMA R0, R1, R2, R3 ;\nFMUL.FTZ R0, R1, R2 ;\nFENCE.VIEW.ASYNC.UNKNOWN ;'
    result=audit_sass(source,exact=('FENCE.VIEW.ASYNC.S',))
    assert result['floatOps']=={}
    assert result['violations']==['FFMA R0, R1, R2, R3 ;','FMUL.FTZ R0, R1, R2 ;','FENCE.VIEW.ASYNC.UNKNOWN ;']
    assert audit_sass('FENCE.VIEW.ASYNC.S ;')['violations']==['FENCE.VIEW.ASYNC.S ;']
