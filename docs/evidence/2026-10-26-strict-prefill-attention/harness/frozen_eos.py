"""Reuse a sealed uncaptured oracle only after the complete finite experiment agrees.

The caller still executes the new captured EOS path. This never labels the sealed oracle as a new native run.
"""
import copy


def bind_control(actual, expected, eos):
    fields = ('model', 'modelFiles', 'schemaHash', 'parentSha256', 'noiseEngine', 'seed', 'sigma', 'chatWorkloadSha256')
    if any(actual.get(k) != expected.get(k) or k not in expected for k in fields):
        raise ValueError('Sealed EOS control belongs to a different experiment')
    cases = actual['cases']
    if [c['state'] for c in cases] != ['parent', 'plus', 'minus', 'restored'] or len(expected['cases']) != 4:
        raise ValueError('Incomplete parent/canonical pair/restore check')
    for now, old in zip(cases, expected['cases']):
        if (not now['restoreExact'] or not now['tileEqualsStream'] or
            any(now[k] != old[k] for k in ('state', 'weightsSha256', 'results'))):
            raise ValueError('New trained parity differs from the sealed control')
    control = expected['eosCheck']
    if (not control['equal'] or control['captured'] != control['uncaptured'] or
        any(eos[k] != control[k] for k in ('eosTokenIds', 'maxNewTokens'))):
        raise ValueError('EOS options or the sealed captured/uncaptured comparison differ')
    return copy.deepcopy(control['uncaptured'])
