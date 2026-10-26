"""Identity-gated finite FP16 vendor projection comparison; no universal equality claim."""
def compare(left,right):
    for data in (left,right):
        if data['status']!='ok' or not data['finalRestoreExact']:raise ValueError('Incomplete or bad restore')
    for key in ('sourceSha256','modelFilesHash','workloadSha256','schemaHash','parentSha256','promptTokenIds','settings'):
        if left[key]!=right[key]:raise ValueError('Mismatched '+key)
    def indexed(data):
        cases={}
        for case in data['cases']:
            key=(case['state'],case['policy'],case['batch'])
            if key in cases:raise ValueError('Duplicate case')
            cases[key]=case
        return cases
    a,b=indexed(left),indexed(right)
    if a.keys()!=b.keys():raise ValueError('Mismatched cases')
    result={'cases':[],'rows':0,'tokenRowsDifferent':0,'rewardFlips':0}
    for key,ca in a.items():
        cb=b[key]
        if ca['weightsSha256']!=cb['weightsSha256']or ca['flags']!=cb['flags']:raise ValueError('Candidate/flag mismatch')
        if len(ca['outputs'])!=len(cb['outputs']):raise ValueError('Row count mismatch')
        differences=[];flips=0
        for x,y in zip(ca['outputs'],cb['outputs'],strict=True):
            if x['id']!=y['id']:raise ValueError('Row identity mismatch')
            flip=x['reward']!=y['reward'];flips+=flip
            if x['tokens']!=y['tokens']:
                first=next((i for i,(u,v)in enumerate(zip(x['tokens'],y['tokens']))if u!=v),min(len(x['tokens']),len(y['tokens'])))
                differences.append({'id':x['id'],'firstDivergence':first,'leftToken':x['tokens'][first]if first<len(x['tokens'])else None,
                                    'rightToken':y['tokens'][first]if first<len(y['tokens'])else None,
                                    'rewardFlip':flip,'bothFinished':x['finished']and y['finished']})
        result['cases'].append({'state':key[0],'policy':key[1],'batch':key[2],'rows':len(ca['outputs']),
                                'tokenRowsDifferent':len(differences),'rewardFlips':flips,'differences':differences})
        result['rows']+=len(ca['outputs']);result['tokenRowsDifferent']+=len(differences);result['rewardFlips']+=flips
    return result
