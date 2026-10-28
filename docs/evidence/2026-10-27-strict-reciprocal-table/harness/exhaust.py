"""Exhaust all positive FP32 bit patterns in the declared reciprocal domain, in bounded CPU slabs."""
import argparse,hashlib,json,time
from pathlib import Path
import numpy as np
from lookup import build_table,newton

p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);a=p.parse_args();assert not a.out.exists()
t=time.perf_counter();table=build_table();rows=[];count=0
for exponent in range(27,227):
    tested=0
    for first in range(0,1<<23,1<<20):
        bits=np.arange(first,first+(1<<20),dtype=np.uint32)|(np.uint32(exponent)<<23)
        values=bits.view(np.float32)
        bits=bits[(values>=np.float32(1e-30))&(values<=np.float32(1e30))]
        expected=newton(bits)
        actual=(table[bits&0x7FFFFF].astype(np.int64)-((exponent-127)<<23)).astype(np.uint32)
        assert np.array_equal(actual,expected),exponent
        tested+=len(bits)
    count+=tested;rows.append({'exponentField':exponent,'bitPatterns':tested})
    if exponent%10==0:print('exponent',exponent,'patterns',count,flush=True)
report={'status':'ok','tableBytes':table.nbytes,'tableSha256':hashlib.sha256(table.tobytes()).hexdigest(),'positiveFp32PatternsTested':count,'exponents':rows,'wallSeconds':time.perf_counter()-t,'limits':'CPU NumPy separate FP32 primitives, plus sampled independent Torch reference tests. No GPU speed or decoder/platform qualification.'}
with a.out.open('x') as f:json.dump(report,f,indent=2);f.write('\n')
print(json.dumps({k:v for k,v in report.items() if k!='exponents'}),flush=True)
