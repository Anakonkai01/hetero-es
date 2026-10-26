import copy

import pytest

from frozen_eos import bind_control


def receipt():
    return dict(model='qwen', modelFiles={'weights': 'a'}, schemaHash='schema', parentSha256='parent',
                noiseEngine='v2', seed=7001, sigma=0.001, chatWorkloadSha256='prompts',
                cases=[dict(state=s, weightsSha256=s, restoreExact=True, tileEqualsStream=True,
                            results={'stream': {'tokens': [1, 2]}, 'tile': {'tokens': [1, 2]}})
                       for s in ('parent', 'plus', 'minus', 'restored')],
                eosCheck=dict(eosTokenIds=[2], maxNewTokens=370, equal=True,
                              captured={'tokens': [[1, 2]], 'tokensSha256': 'tokens'},
                              uncaptured={'tokens': [[1, 2]], 'tokensSha256': 'tokens'}))


def test_control_requires_the_same_complete_finite_experiment_and_returns_a_copy():
    expected = receipt()
    result = bind_control(receipt(), expected, {'eosTokenIds': [2], 'maxNewTokens': 370})
    result['tokens'][0][0] = 9
    assert expected['eosCheck']['uncaptured']['tokens'] == [[1, 2]]


@pytest.mark.parametrize('field', ['modelFiles', 'schemaHash', 'parentSha256', 'noiseEngine', 'seed', 'sigma', 'chatWorkloadSha256'])
def test_changed_experiment_cannot_reuse_a_control(field):
    actual, expected = receipt(), receipt()
    actual[field] = 'different'
    with pytest.raises(ValueError):
        bind_control(actual, expected, {'eosTokenIds': [2], 'maxNewTokens': 370})


@pytest.mark.parametrize('kind', ['tokens', 'weights', 'restore', 'missing_state', 'control_mismatch', 'eos', 'length'])
def test_incomplete_parity_or_a_different_eos_contract_cannot_reuse_a_control(kind):
    actual, expected = receipt(), receipt()
    eos = {'eosTokenIds': [2], 'maxNewTokens': 370}
    if kind == 'tokens': actual['cases'][1]['results']['stream']['tokens'][0] = 9
    elif kind == 'weights': actual['cases'][2]['weightsSha256'] = 'wrong'
    elif kind == 'restore': actual['cases'][3]['restoreExact'] = False
    elif kind == 'missing_state': actual['cases'].pop()
    elif kind == 'control_mismatch': expected['eosCheck']['uncaptured']['tokens'][0][0] = 9
    elif kind == 'eos': eos['eosTokenIds'] = [3]
    else: eos['maxNewTokens'] = 128
    with pytest.raises(ValueError): bind_control(actual, expected, eos)
