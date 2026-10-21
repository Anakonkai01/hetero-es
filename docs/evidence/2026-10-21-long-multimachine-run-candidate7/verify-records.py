"""Independent context/update reconstruction from the CUDA parity receipt and pinned inputs.

No training or ledger writes. The separate candidate verifier must have succeeded first.
Candidate7 adds the elastic checks (ADR-009): no committed result from a non-member, exactly one JOIN then one LEAVE of
the joining worker, which committed results in between, and explicit expiry rows of the failed worker, each followed by
a committed result of a later attempt.
"""
import argparse,json,sqlite3
from pathlib import Path
from heteroes.generation_record import GenerationRecord
from heteroes.ledger import GenerationResults,Ledger
from heteroes.product.membership import membership_violations
from heteroes.v3.data import open_dataset
from heteroes.v3.run import RecipeV3Run

p=argparse.ArgumentParser()
for n in ('run','parity','experiment','out'):p.add_argument(n)
p.add_argument('--generations',type=int,default=50)
p.add_argument('--joiner',required=True)
p.add_argument('--failed-worker',required=True)
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
with Ledger(root/'ledger.sqlite') as ledger,sqlite3.connect(f'file:{root / "ledger.sqlite"}?mode=ro',uri=True) as db:
 violations=membership_violations(ledger,a.experiment)
 changes=[(c.worker_id,c.action,c.effective_generation) for c in ledger.list_membership(a.experiment)]
 joiner=[c for c in changes if c[0]==a.joiner]
 commits=[g for g,_,w in ledger.list_committed_attempts(a.experiment) if w==a.joiner]
 expired=[e for e in ledger.list_expired(a.experiment) if e[2]==a.failed_worker]
 # Every expired attempt must be taken over: a later attempt of the same candidate is the committed one.
 retried=[db.execute('select attempt_number from result where candidate_id=?',(e[0],)).fetchone() for e in expired]
 elastic={'membershipViolations':violations,'membershipChanges':changes,'joinerCommitGenerations':sorted(set(commits)),
  'failedWorkerExpiries':[{'candidateId':e[0],'attempt':e[1],'retriedBy':r[0] if r else None} for e,r in zip(expired,retried)]}
 elastic['ok']=(violations==[] and [c[1] for c in joiner]==['JOIN','LEAVE'] and joiner[0][2]<joiner[1][2]
  and bool(commits) and all(joiner[0][2]<=g<joiner[1][2] for g in commits)
  and bool(expired) and all(r is not None and r[0]>e[1] for e,r in zip(expired,retried)))
out={'allEqual':all(c['contextEqual'] and c['recordEqual'] and c['recordHashEqual'] for c in checks) and elastic['ok'],'elastic':elastic,'generations':checks}
with Path(a.out).open('x') as f:json.dump(out,f,indent=1);f.write('\n')
print('ALL CONTEXTS, RECORDS AND MEMBERSHIP CHECKS PASS' if out['allEqual'] else 'DIFFERENCES FOUND')
raise SystemExit(0 if out['allEqual'] else 1)
