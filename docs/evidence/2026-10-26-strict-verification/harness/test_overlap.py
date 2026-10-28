from overlap import simulate

def test_prior_tokens_need_verification_and_wrong_tail_is_rejected():
    result=simulate([[1,2,3,4,5,6]],[1,2,3,4,99,6],block=4,min_match=2,max_match=4)
    assert result['emitted']==[1,2,3,4,99,6]
    assert result['rounds']==3
    assert result['acceptedDraftTokens']==2

def test_no_match_uses_single_token_steps():
    result=simulate([[8,9,10]],[1,2,3,4],block=4,min_match=2,max_match=4)
    assert result['rounds']==3 and result['verifiedPositions']==3
    assert result['acceptedDraftTokens']==0

def test_matching_prior_trace_finishes_without_adding_a_bonus_after_the_end():
    result=simulate([[1,2,3,4,5,6]],[1,2,3,4,5,6],block=4,min_match=2,max_match=4)
    assert result['rounds']==2 and result['acceptedDraftTokens']==3
    assert result['emitted']==[1,2,3,4,5,6]
