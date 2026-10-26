import pytest
from speculative import SuffixProposer

def test_longest_suffix_and_latest_prior_are_selected_with_bounded_proposal():
    proposer=SuffixProposer([[[1,2,3,4,5],[1,2,3,9,8]],[[7,8,10]]])
    assert proposer(0,(77,1,2,3),1)==(9,)
    assert proposer(0,(1,2),3)==(3,9,8)
    assert proposer(1,(7,8),3)==(10,)
    assert proposer(0,(1,2,3),0)==()
    assert proposer(0,(55,66),3)==()

def test_proposal_bank_enforces_source_budget_and_integer_tokens():
    with pytest.raises(ValueError,match='budget'):SuffixProposer([[[1,2,3]]],max_source_tokens=2)
    for sequence in ([1,-1],[1,True],[1,2.]):
        with pytest.raises(ValueError,match='token'):SuffixProposer([[sequence]])
    with pytest.raises(ValueError,match='suffix'):SuffixProposer([],min_match=3,max_match=2)
