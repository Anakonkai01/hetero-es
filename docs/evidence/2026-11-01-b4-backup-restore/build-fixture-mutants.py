import json
from pathlib import Path
items=[
('experiment fixture inserts depend on the old column count','scripts/serve-test-lab.py','INSERT INTO experiments(id,owner,body,snapshot) VALUES (?,?,?,?)','INSERT INTO experiments VALUES (?,?,?,?)'),
('assignment fixture inserts depend on the old column count','scripts/serve-test-lab.py','INSERT INTO assignments(id,run_id,coordinator,epoch,body,snapshot,released) VALUES (?,?,?,?,?,?,0)','INSERT INTO assignments VALUES (?,?,?,?,?,?,0)'),
('fixture startup failures disappear from the overall result','scripts/check-all.sh','  failed+=("fixture-lab-$port")','  :'),
('fixture startup diagnostics vanish with temporary cleanup','scripts/check-all.sh','> "$OUT/lab-$port.log" 2>&1 &','> "$WORK/lab-$port.log" 2>&1 &'),
]
mutants=[dict(name=n,file=f,old=o,new=v) for n,f,o,v in items]
for m in mutants:assert Path(m['file']).read_text().count(m['old'])==1,m['name']
Path('.scratch/review-2026-11/B4/fixture-mutants.json').write_text(json.dumps(mutants,indent=2)+'\n')
