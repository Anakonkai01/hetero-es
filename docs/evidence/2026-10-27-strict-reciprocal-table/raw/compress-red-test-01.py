"""Same five rounded Newton steps, reduced to a normalized mantissa table and exponent adjustment."""
import numpy as np
import pytest
import torch
from heteroes.eval.reference_ops import reciprocal
from lookup import build_table,lookup

@pytest.fixture(scope='module')
def table():return build_table()

def test_normalized_table_and_powers_of_two_match_cpu_reference(table):
    values=torch.tensor([1e-30,1e-20,.5,1.,1.0000001192092896,2.,3.,32.,1e20,1e30])
    actual=lookup(values.numpy(),table)
    assert np.array_equal(actual.view(np.uint32),reciprocal(values).numpy().view(np.uint32))
    assert table.dtype==np.uint32 and table.shape==(1<<23,) and table.nbytes==32*1024**2

def test_every_exponent_has_identical_normalization_at_boundaries_and_sampled_mantissas(table):
    mant=np.array([0,1,2,3,0x73ffff,0x7fffff,*range(0,1<<23,17189)],dtype=np.uint32)
    for exponent in range(27,227):
        bits=(np.uint32(exponent)<<23)|mant
        values=bits.view(np.float32);values=values[(values>=np.float32(1e-30))&(values<=np.float32(1e30))]
        expected=reciprocal(torch.from_numpy(values.copy())).numpy().view(np.uint32)
        assert np.array_equal(lookup(values,table).view(np.uint32),expected),exponent

def test_rejects_outside_declared_cpu_probe_domain(table):
    for x in (-1.,0.,float('inf'),float('nan'),1e-31,1e31):
        with pytest.raises(ValueError):lookup(np.array([x],dtype=np.float32),table)

def test_compressed_table_reconstructs_every_mantissa_exactly(table):
    from compressed import compress,unpack
    anchors,packed=compress(table)
    assert anchors.nbytes+packed.nbytes < 5*1024**2
    mantissas=np.arange(1<<23,dtype=np.uint32)
    assert np.array_equal(unpack(mantissas,anchors,packed),table)
