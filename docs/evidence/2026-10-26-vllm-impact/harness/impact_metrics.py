"""Finite paired-output effects on rewards and hypothetical ES coefficients; no weight update."""
from itertools import combinations, product

import numpy as np

from heteroes.eval.workload import extract_integer
from heteroes.study.evaluation import extract
from heteroes.v3.antithetic import merged_update
from heteroes.v3.coefficients import coefficients_for, centered_rank


def output_impact(rows, left, right):
    if not len(rows)==len(left)==len(right) or not rows:
        raise ValueError('Nonempty aligned output rows required')
    for row,a,b in zip(rows,left,right,strict=True):
        if row['id']!=a['id'] or row['id']!=b['id']:
            raise ValueError('Mismatched row identity')
    details=[]
    for row,a,b in zip(rows,left,right,strict=True):
        target=row['answer']
        parse=extract_integer if row['scorer']=='last-integer' else extract
        aa,bb=parse(a['text']),parse(b['text'])
        truth=None if target is None else int(target) if row['scorer']=='last-integer' else str(target)
        details.append({'id':row['id'],'group':row['group'],'scored':target is not None,
                        'tokenEqual':a['tokens']==b['tokens'],'textEqual':a['text']==b['text'],
                        'leftPrediction':aa,'rightPrediction':bb,'expected':truth,
                        'leftReward':None if target is None else float(aa==truth),
                        'rightReward':None if target is None else float(bb==truth),
                        'leftTruncated':a.get('finishReason')=='length','rightTruncated':b.get('finishReason')=='length'})
    result={}
    for group in ['all',*sorted({r['group'] for r in rows})]:
        subset=[d for d in details if group=='all' or d['group']==group]
        scored=[d for d in subset if d['scored']]
        n=len(scored)
        ac=sum(d['leftReward'] for d in scored);bc=sum(d['rightReward'] for d in scored)
        result[group]={'rows':len(subset),'scorable':n,'tokenRowsDifferent':sum(not d['tokenEqual'] for d in subset),
                       'textRowsDifferent':sum(not d['textEqual'] for d in subset),
                       'predictionDifferentScored':sum(d['leftPrediction']!=d['rightPrediction'] for d in scored),
                       'rewardFlips':sum(d['leftReward']!=d['rightReward'] for d in scored),
                       'leftCorrect':ac,'rightCorrect':bc,'accuracyDeltaPp':100*(bc-ac)/n if n else None,
                       'leftReward':ac/n if n else None,'rightReward':bc/n if n else None,
                       'leftTruncated':sum(d['leftTruncated'] for d in subset),
                       'rightTruncated':sum(d['rightTruncated'] for d in subset),
                       'differentCases':[d for d in subset if not d['tokenEqual'] or not d['textEqual']]}
    return result


def cosine(a,b,gram=None):
    gram=np.eye(len(a)) if gram is None else gram
    na=float(a @ gram @ a);nb=float(b @ gram @ b)
    if na<=1e-24 or nb<=1e-24:
        return None
    return float(np.clip((a @ gram @ b)/np.sqrt(na*nb),-1,1))


def population_impact(left,right,gram=None):
    a,b=np.asarray(left,dtype=np.float64),np.asarray(right,dtype=np.float64)
    if a.ndim!=1 or b.shape!=a.shape or not len(a) or len(a)%2 or len(a)>12 or not np.isfinite(a).all() or not np.isfinite(b).all():
        raise ValueError('Matching finite antithetic populations required')
    n=len(a)
    best=lambda x:np.flatnonzero(x==x.max()).tolist()
    rel=lambda d:int(d>0)-int(d<0)
    pairs=[(rel(a[i]-a[j]),rel(b[i]-b[j])) for i,j in combinations(range(n),2)]
    result={'leftRewards':a.tolist(),'rightRewards':b.tolist(),
            'maxAbsRewardDelta':float(np.max(np.abs(a-b))),
            'candidateRewardStdLeft':float(a.std()),'candidateRewardStdRight':float(b.std()),
            'strictPairInversions':sum(x*y<0 for x,y in pairs),
            'tieStatusChanges':sum((x==0)!=(y==0) for x,y in pairs),
            'bestSetLeft':best(a),'bestSetRight':best(b),
            'spearmanWithAverageTies':cosine(centered_rank(a).astype(float),centered_rank(b).astype(float)),
            'rules':{}}
    for rule in ('zscore@1','centered-rank@1'):
        descriptors=[(7001+i//2,1 if i%2==0 else -1) for i in range(n)]
        c=coefficients_for(rule,a,1e-8);d=coefficients_for(rule,b,1e-8)
        base=merged_update(descriptors,c)[1].astype(np.float64)
        other=merged_update(descriptors,d)[1].astype(np.float64)
        values=[];sampled=[];new_signal=0;best_changes=0;max_delta=0
        for assignment in product((0,1),repeat=n):
            mixed=np.where(assignment,b,a)
            mc=coefficients_for(rule,mixed,1e-8)
            merged=merged_update(descriptors,mc)[1].astype(np.float64)
            angle=cosine(base,merged)
            if angle is not None:values.append(angle)
            angle=cosine(base,merged,gram)
            if angle is not None:sampled.append(angle)
            new_signal+=bool(np.linalg.norm(base)==0 and np.linalg.norm(merged)>0)
            best_changes+=best(mixed)!=best(a)
            max_delta=max(max_delta,float(np.max(np.abs(mc-c))))
        result['rules'][rule]={'leftCoefficients':c.tolist(),'rightCoefficients':d.tolist(),
                              'leftMergedCoefficients':base.tolist(),'rightMergedCoefficients':other.tolist(),
                              'referenceHasSignal':bool(np.linalg.norm(base)>0),
                              'allOtherMergedCoefficientCosine':cosine(base,other),
                              'sampledCanonicalDirectionCosine':cosine(base,other,gram) if gram is not None else None,
                              'mixedAssignments':2**n,'mixedAssignmentsWithNewSignal':new_signal,
                              'mixedAssignmentsChangingBestSet':best_changes,'maxAbsMixedCoefficientDelta':max_delta,
                              'minimumMergedCoefficientCosine':min(values) if values else None,
                              'minimumSampledDirectionCosine':min(sampled) if sampled and gram is not None else None}
    return result
