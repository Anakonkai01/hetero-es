from audit import audit_integer
from heteroes.eval import strict_cuda as sc

def test_only_exact_async_memory_fence_is_added_to_the_existing_integer_policy():
    mma='IMMA.16832.S8.S8 R0, R2.ROW, R4.COL, R0 ;'
    assert audit_integer(mma)==sc.audit_integer_sass(mma)
    source=mma+'\nFENCE.VIEW.ASYNC.S ;\nFFMA R0, R1, R2, R3 ;\nFMUL R0, R1, R2 ;\nMUFU.RCP R0, R1 ;\nFENCE.VIEW.ASYNC.UNKNOWN ;'
    result=audit_integer(source)
    assert result['integerMmaOps']==1
    assert result['violations']==['FFMA R0, R1, R2, R3 ;','MUFU.RCP R0, R1 ;','FENCE.VIEW.ASYNC.UNKNOWN ;','Floating multiply in integer projection']
    assert audit_integer('FENCE.VIEW.ASYNC.S ;')['violations']==['Missing integer IMMA']
