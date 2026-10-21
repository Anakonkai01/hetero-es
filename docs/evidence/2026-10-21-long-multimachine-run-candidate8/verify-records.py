"""Independent context/update reconstruction from the CUDA parity receipt and pinned inputs, plus the candidate8
elastic checks (ADR-009 items 1-8) on the private ledger copy. No training or ledger writes. The separate candidate
verifier (`verify_managed_run.py`) must have succeeded first.

Elastic checks: no committed result from a non-member; the joining worker's JOIN/LEAVE/JOIN sequence with strictly
increasing effective generations and committed results only (and at least once) inside its member windows; every worker
named in --expiry-workers has explicit `expiry` rows, none of those attempts was committed, and each candidate was
committed by a later attempt; every worker named in --restart-workers was started again BY THE SYSTEM (a
`worker_restarted` lifecycle event with launch >= 1, no manual membership change for it, and a result committed by an
attempt leased after that event); exactly one committed result per candidate.
"""
import argparse,json,sqlite3,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from elastic_checks import elastic_checks
from heteroes.generation_record import GenerationRecord
from heteroes.ledger import GenerationResults,Ledger
from heteroes.v3.data import open_dataset
from heteroes.v3.run import RecipeV3Run

p=argparse.ArgumentParser()
for n in ('run','parity','experiment','out'):p.add_argument(n)
p.add_argument('--generations',type=int,default=50)
p.add_argument('--joiner',required=True)
p.add_argument('--expiry-workers',required=True,help='comma list: workers with expected expiry rows')
p.add_argument('--restart-workers',required=True,help='comma list: workers that must have been restarted automatically')
p.add_argument('--lifecycle',required=True)
p.add_argument('--joiner-changes',default='JOIN,LEAVE,JOIN')
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
elastic=elastic_checks(root,a.experiment,a.generations,plan['population'],a.joiner,a.joiner_changes,a.expiry_workers,a.restart_workers,a.lifecycle)
out={'allEqual':all(c['contextEqual'] and c['recordEqual'] and c['recordHashEqual'] for c in checks) and elastic['ok'],'elastic':elastic,'generations':checks}
with Path(a.out).open('x') as f:json.dump(out,f,indent=1);f.write('\n')
print('ALL CONTEXTS, RECORDS AND MEMBERSHIP CHECKS PASS' if out['allEqual'] else 'DIFFERENCES FOUND')
raise SystemExit(0 if out['allEqual'] else 1)
