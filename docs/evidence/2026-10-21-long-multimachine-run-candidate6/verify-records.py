"""Independent context/update reconstruction from the CUDA parity receipt and pinned inputs.

No training or ledger writes. The separate candidate verifier must have succeeded first.
"""
import argparse,json,sqlite3
from pathlib import Path
from heteroes.generation_record import GenerationRecord
from heteroes.ledger import GenerationResults,Ledger
from heteroes.v3.data import open_dataset
from heteroes.v3.run import RecipeV3Run

p=argparse.ArgumentParser()
for n in ('run','parity','experiment','out'):p.add_argument(n)
p.add_argument('--generations',type=int,default=50)
a=p.parse_args();root=Path(a.run)
parity=json.loads(Path(a.parity).read_text());assert parity['allEqual']
recipe=json.loads((root/'recipe.json').read_text());plan=json.loads((root/'plan.json').read_text())
run=RecipeV3Run(recipe,plan);assert not run.update_rule,'This receipt is for the declared plain update'
data=open_dataset(root/'dataset.json');checks=[]
assert len(parity['generations'])==a.generations
with Ledger(root/'ledger.sqlite') as ledger,sqlite3.connect(f'file:{root / "ledger.sqlite"}?mode=ro',uri=True) as db:
 assert len(ledger.list_generations(a.experiment))==a.generations
 for g in parity['generations']:
  n=g['generation'];records=ledger.list_candidates(a.experiment,n)
  assert len(records)==plan['population']==len(g['candidates'])
  assert all(c['rewardEqual'] and c['textsEqual'] and c['textsHashEqual'] for c in g['candidates'])
  # These rewards were individually compared with independent CUDA regeneration/scoring by the candidate verifier.
  rewards=tuple(c['reward'] for c in g['candidates'])
  results=GenerationResults(run.hash,g['parentSha256'],tuple(r.descriptor.seed for r in records),rewards,tuple(r.descriptor.sign for r in records))
  rebuilt=GenerationRecord.from_results(a.experiment,n,results,alpha=run.alpha_at(n),eta=run.reward_eta,coefficient_rule=run.coefficient_rule)
  saved=ledger.get_update(a.experiment,n)
  context=json.loads(db.execute('select body from generation_context where experiment_id=? and generation=?',(a.experiment,n)).fetchone()[0])
  # A wrong coefficient/alpha/context cannot pass merely because recorded rewards happened to match.
  checks.append({'generation':n,'contextEqual':run.context(data,n)==context,'recordEqual':rebuilt.to_json()==saved.record.to_json(),'recordHashEqual':rebuilt.hash==saved.record_hash,'recordHash':rebuilt.hash})
assert len(checks)==a.generations
out={'allEqual':all(c['contextEqual'] and c['recordEqual'] and c['recordHashEqual'] for c in checks),'generations':checks}
with Path(a.out).open('x') as f:json.dump(out,f,indent=1);f.write('\n')
print('ALL CONTEXTS AND RECORDS EQUAL' if out['allEqual'] else 'DIFFERENCES FOUND')
raise SystemExit(0 if out['allEqual'] else 1)
