"""Offline prior-completion suffix proposals; target trace is used only as a simulated verifier."""
def simulate(priors,target,*,block,min_match=2,max_match=8):
    if not target or block<1 or not 1<=min_match<=max_match:raise ValueError('Invalid finite trace settings')
    lookup={}
    for prior in priors:
        for n in range(min_match,max_match+1):
            for first in range(len(prior)-n):
                lookup[tuple(prior[first:first+n])]=prior[first+n:first+n+block-1]
    position=1;rounds=positions=accepted=0;emitted=target[:1];advances=[]
    while position<len(target):
        draft=[]
        for n in range(min(max_match,position),min_match-1,-1):
            draft=lookup.get(tuple(emitted[-n:]),[])
            if draft:break
        draft=draft[:max(0,len(target)-position-1)]
        matched=0
        for guess,truth in zip(draft,target[position:]):
            if guess!=truth:break
            matched+=1
        advance=min(len(target)-position,matched+1)
        # Only target-verified prefix and the verifier's next token are emitted.
        emitted.extend(target[position:position+advance]);position+=advance
        rounds+=1;positions+=len(draft)+1;accepted+=matched;advances.append(advance)
    assert emitted==target
    return {'rounds':rounds,'verifiedPositions':positions,'acceptedDraftTokens':accepted,
            'emitted':emitted,'advances':advances}
