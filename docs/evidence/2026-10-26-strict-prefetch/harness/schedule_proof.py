"""Symbolic copy-address/schedule check for every admitted K tile count and split specialization."""
import hashlib
import json
from pathlib import Path

out=Path('docs/evidence/2026-10-26-strict-prefetch/schedule-proof-01.json')
assert not out.exists()
cases=reads=0
for stages in (2,4,8):
    for tiles in range(0,1025):
        for split in (1,2,4,8):
            for z in range(split):
                shared=[None]*stages
                pending=[(i,z+i*split) for i in range(stages-1)]
                phase=0
                for chunk in range(z,tiles,split):
                    while len(pending)>stages-2:
                        slot,value=pending.pop(0);shared[slot]=value
                    assert shared[phase]==chunk,(stages,tiles,split,z,chunk,shared)
                    reads+=1
                    future=(phase+stages-1)&(stages-1)
                    pending.append((future,chunk+(stages-1)*split))
                    assert len(pending)<=7
                    phase=(phase+1)&(stages-1)
                while pending:
                    slot,value=pending.pop(0);shared[slot]=value
                assert not pending
                cases+=1
# Each thread owns sixteen bytes per stage; its two eight-byte copies are disjoint and aligned.
for stages in (2,4,8):
    for warps in (4,8):
        owners={}
        for stage in range(stages):
            for thread in range(32*warps):
                for word in (0,1):
                    offset=((stage*32*warps+thread)*4+word*2)*4
                    assert offset%8==0
                    for byte in range(offset,offset+8):
                        assert byte not in owners
                        owners[byte]=(stage,thread,word)
        assert len(owners)==stages*32*warps*16
report={'status':'ok','tileCounts':[0,1024],'maxWidth':32768,'stages':[2,4,8],'splitK':[1,2,4,8],
        'scheduleCases':cases,'symbolicReads':reads,'pendingGroupsAtMost':7,
        'disjointAlignedThreadPrivateSharedCopies':True,
        'sourceSha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'limits':'Algorithmic address/order argument, not a compiler/GPU/quality theorem. GPU oracle and instruction audits remain required.'}
with out.open('x') as f:json.dump(report,f,indent=2);f.write('\n')
print(json.dumps(report))
