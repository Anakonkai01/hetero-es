import numpy as np
from lookup import build_table
from compressed import compress,unpack

def test_compressed_table_reconstructs_every_mantissa_exactly():
    table=build_table();anchors,packed=compress(table)
    assert anchors.nbytes+packed.nbytes < 5*1024**2
    mantissas=np.arange(1<<23,dtype=np.uint32)
    assert np.array_equal(unpack(mantissas,anchors,packed),table)
