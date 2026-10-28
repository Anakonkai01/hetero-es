import numpy as np
import pytest

from impact_metrics import output_impact, population_impact


def rows_fixture():
    rows=[{'id':'a','group':'math','answer':'4','scorer':'last-integer'},
          {'id':'b','group':'math','answer':'8','scorer':'last-integer'},
          {'id':'free','group':'free','answer':None,'scorer':'last-integer'}]
    a=[{'id':'a','tokens':[1,2],'text':'4','finishReason':'stop'},
       {'id':'b','tokens':[3,4],'text':'8','finishReason':'stop'},
       {'id':'free','tokens':[5],'text':'hello','finishReason':'stop'}]
    return rows,a


def test_changed_words_with_same_answer_do_not_become_a_reward_flip():
    rows,a=rows_fixture();b=[dict(x) for x in a]
    b[0].update(tokens=[7,8],text='After checking, 4')
    b[2].update(tokens=[9],text='bonjour')
    result=output_impact(rows,a,b)['all']
    assert result['tokenRowsDifferent']==2
    assert result['predictionDifferentScored']==0
    assert result['rewardFlips']==0 and result['scorable']==2


def test_equal_total_accuracy_can_hide_two_opposing_reward_flips():
    rows,a=rows_fixture();b=[dict(x) for x in a]
    a[1].update(tokens=[0],text='9')
    b[0].update(tokens=[0],text='5')
    result=output_impact(rows,a,b)['all']
    assert result['leftCorrect']==result['rightCorrect']==1
    assert result['rewardFlips']==2 and result['accuracyDeltaPp']==0


def test_misaligned_or_missing_rows_are_rejected():
    rows,a=rows_fixture()
    with pytest.raises(ValueError):output_impact(rows,a,a[:-1])
    with pytest.raises(ValueError):output_impact(rows,a,list(reversed(a)))


def test_repeated_weights_scores_produce_same_order_and_every_assignment_same_update():
    x=[0.1,0.2,0.4,0.3]
    result=population_impact(x,x)
    assert result['strictPairInversions']==0 and result['tieStatusChanges']==0
    assert result['bestSetLeft']==result['bestSetRight']==[2]
    assert result['rules']['zscore@1']['mixedAssignments']==16
    assert result['rules']['zscore@1']['minimumMergedCoefficientCosine'] == pytest.approx(1)
    assert result['rules']['centered-rank@1']['leftMergedCoefficients']==pytest.approx([-1/6,1/6])


def test_tiny_reward_differences_can_reverse_the_antithetic_update():
    result=population_impact([.5,.501,.5,.501],[.5,.499,.5,.499])
    assert result['maxAbsRewardDelta']==pytest.approx(.002)
    assert result['rules']['zscore@1']['allOtherMergedCoefficientCosine']==pytest.approx(-1)
    assert result['strictPairInversions']>0


def test_flat_population_does_not_report_a_fake_direction():
    result=population_impact([0,0,0,0],[0,0,0,0])
    assert result['rules']['zscore@1']['minimumMergedCoefficientCosine'] is None
    assert result['rules']['zscore@1']['referenceHasSignal'] is False


def test_new_signal_on_other_gpu_is_reported_when_reference_is_flat():
    result=population_impact([0,0,0,0],[0,.1,0,0])
    assert result['rules']['zscore@1']['mixedAssignmentsWithNewSignal']>0


def test_gpu_bias_that_cancels_with_one_gpu_can_reverse_a_mixed_assignment():
    result=population_impact([0,.1,0,.1],[.2,.3,.2,.3])
    assert result['rules']['zscore@1']['allOtherMergedCoefficientCosine']==pytest.approx(1)
    assert result['rules']['zscore@1']['minimumMergedCoefficientCosine']==pytest.approx(-1)


@pytest.mark.parametrize('other', [[1,2], [1,2,3,float('nan')]])
def test_invalid_populations_fail(other):
    with pytest.raises(ValueError):population_impact([1,2,3,4],other)
