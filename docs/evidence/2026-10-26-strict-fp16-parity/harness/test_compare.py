import copy
import pytest
from compare_fp16 import compare

def fixture():
    common={'status':'ok','sourceSha256':'source','modelFilesHash':'model','workloadSha256':'workload',
            'schemaHash':'schema','parentSha256':'parent','promptTokenIds':[[1,2]],
            'settings':{'tokens':3},'finalRestoreExact':True,
            'cases':[{'state':'parent','policy':'fp32_acc','batch':1,'weightsSha256':'parent','flags':{},
                      'outputs':[{'id':'q1','tokens':[3,4,5],'reward':1.,'finished':True}]}]}
    common['cases'].append({**common['cases'][0],'state':'restored'})
    return common

def test_same_reward_does_not_hide_token_divergence():
    left=fixture();right=copy.deepcopy(left)
    right['cases'][0]['outputs'][0]['tokens']=[3,7,5]
    right['cases'][1]['outputs'][0]['tokens']=[3,7,5]
    result=compare(left,right)
    assert result['tokenRowsDifferent']==2 and result['rewardFlips']==0
    assert result['cases'][0]['differences'][0]['firstDivergence']==1

def test_candidate_identity_and_exact_restore_are_required():
    for field in ('schemaHash','workloadSha256','modelFilesHash'):
        left=fixture();right=copy.deepcopy(left);right[field]='other'
        with pytest.raises(ValueError):compare(left,right)
    right=fixture();right['cases'][0]['weightsSha256']='other'
    with pytest.raises(ValueError):compare(fixture(),right)
    right=fixture();right['finalRestoreExact']=False
    with pytest.raises(ValueError):compare(fixture(),right)
