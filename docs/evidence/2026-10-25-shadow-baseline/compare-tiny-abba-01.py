"""Check the four independent Tiny processes and compute the A/B/B/A aggregate from raw observations."""

import hashlib
import json
from pathlib import Path
import statistics

HERE = Path(__file__).resolve().parent
destination = HERE / 'tiny-abba-comparison-01.json'
if destination.exists():
    raise FileExistsError(destination)
control = json.loads((HERE / 'raw/tiny-hf-shadow-full-01.json').read_text())
summary = {'order': ['a1', 'b1', 'b2', 'a2'], 'a': 'hf-shadow full batch', 'b': 'strict-frozen no head, zero B',
           'scope': 'Separate sequential processes, warmup plus five timed observations per process; B32 only.',
           'inputs': {}, 'jobs': []}
observations = {'a': [], 'b': []}
for label in summary['order']:
    path = HERE / 'raw' / f'tiny-b32-abba-{label}-01.json'
    data = json.loads(path.read_text())
    assert data['status'] == 'ok' and len(data['cases']) == 1
    assert data['modelFiles'] == control['modelFiles']
    assert data['promptTokenIds'] == control['promptTokenIds']
    assert data['benchmarkSourceSha256'] == control['benchmarkSourceSha256']
    for key in ('maxNewTokens', 'maxContext', 'eosStopping', 'prefixCaching', 'repetitionPenalty', 'dtype', 'repeats'):
        assert data['workload'][key] == control['workload'][key]
    for key in ('torch', 'transformers', 'cuda', 'gpu', 'computeCapability', 'matmulAllowTF32'):
        assert data['environment'][key] == control['environment'][key]
    case = data['cases'][0]
    assert case['sequences'] == 32 and case['generatedTokensPerRepeat'] == 1024
    assert case['repeatTokensEqual'] and len(case['seconds']) == 5
    assert len(case['tokens']) == 32 and all(len(row) == 32 for row in case['tokens'])
    assert all(abs(total - refresh - decode) < 1e-9 for total, refresh, decode in
               zip(case['seconds'], case['refreshSeconds'], case['decodeSeconds'], strict=True))
    assert case['tokensPerSecondTotal'] == 1024 / statistics.median(case['seconds'])
    assert data['engine'] == ('hf-shadow' if label.startswith('a') else 'strict-frozen')
    if label.startswith('a'):
        assert data['shadowStorage'] == control['shadowStorage']
        assert all(value > 0 for value in case['refreshSeconds'])
    observations[label[0]].extend(case['seconds'])
    summary['inputs'][path.relative_to(HERE).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    summary['jobs'].append({'label': label, 'tokensPerSecond': case['tokensPerSecondTotal'],
                            'rawSeconds': case['seconds']})
summary['shadowTokensPerSecond'] = 1024 / statistics.median(observations['a'])
summary['frozenTokensPerSecond'] = 1024 / statistics.median(observations['b'])
summary['frozenOverShadow'] = summary['frozenTokensPerSecond'] / summary['shadowTokensPerSecond']
with destination.open('x') as stream:
    json.dump(summary, stream, indent=2)
    stream.write('\n')
print(json.dumps(summary, indent=2))
