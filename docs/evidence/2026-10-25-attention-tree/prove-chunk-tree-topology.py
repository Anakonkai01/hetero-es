"""Exact expression-tree comparison for every admitted attention length, independent of floating values."""
import argparse,json,time,hashlib
from pathlib import Path
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
if a.out.exists():p.error('Fresh output required')
def adjacent(values):
 values=list(values)
 while len(values)>1:values=[(values[i],values[i+1])for i in range(0,len(values)-1,2)]+(values[-1:]if len(values)%2 else[])
 return values[0]
def grouped(values,size):return adjacent([adjacent(values[i:i+size])for i in range(0,len(values),size)])
start=time.perf_counter();checked=0
for count in range(1,4097):
 leaves=list(range(count));expected=adjacent(leaves)
 for size in(8,16):assert expected==grouped(leaves,size),(count,size);checked+=1
r={'status':'ok','sourceSha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'lengths':4096,'chunkSizes':[8,16],'exactTopologyComparisons':checked,'wallSeconds':time.perf_counter()-start,'limits':'Exact symbolic adjacent-pair topology equality for every supported length. Requires source/compiled kernels to implement the shown topology and identical rounded primitives/loads/error checks; not a compiler, device or model-quality theorem.'}
with a.out.open('x')as f:json.dump(r,f,indent=2);f.write('\n')
print(json.dumps(r))
