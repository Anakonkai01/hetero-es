"""Validate the matched workload and compute ratios from raw duration medians, using CPU only."""

import hashlib
import json
from pathlib import Path
import statistics

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
destination = HERE / 'comparison-01.json'
if destination.exists():
    raise FileExistsError(destination)
provenance = json.loads((HERE / 'provenance-01.json').read_text())
previous = json.loads((ROOT / 'docs/evidence/2026-10-25-frozen-audit-perf/model-manifests.json').read_text())
summary = {'scope': 'Local 5070 Ti warmed parent inference plus shadow refresh; five observations; no ES perturb/restore.',
           'measuredCommit': provenance['measuredCommit'], 'comparisons': [], 'inputs': {}, 'tokenComparisons': []}

for model in ('smol', 'tiny', 'qwen'):
    baseline = json.loads((HERE / 'raw' / f'{model}-hf-shadow-full-01.json').read_text())
    config = json.loads((Path('/home/pc5070ti/projects/heteroes/.scratch/strict-integer-20261025/models') /
                         model / 'config.json').read_text())
    frozen_label = 'frozen-head' if config.get('tie_word_embeddings', False) else 'frozen-no-head'
    variants = ['hf-shadow-full', 'hf-shadow-chunk16', 'b22', frozen_label]
    documents = {}
    for label in variants:
        path = HERE / 'raw' / f'{model}-{label}-01.json'
        data = json.loads(path.read_text())
        assert data['status'] == 'ok', path
        assert data['modelFiles'] == baseline['modelFiles'] == previous['models'][model]['files'], path
        assert data['promptTokenIds'] == baseline['promptTokenIds'], path
        assert hashlib.sha256(repr(data['promptTokenIds']).encode()).hexdigest() == previous['models'][model]['promptDigest']
        assert data['benchmarkSourceSha256'] == provenance['benchmarkSha256'], path
        for key in ('maxNewTokens', 'maxContext', 'eosStopping', 'prefixCaching', 'repetitionPenalty', 'dtype', 'repeats'):
            assert data['workload'][key] == baseline['workload'][key], (path, key)
        for key in ('torch', 'transformers', 'cuda', 'gpu', 'computeCapability', 'matmulAllowTF32'):
            assert data['environment'][key] == baseline['environment'][key], (path, key)
        assert data['workload']['repeats'] == 5
        if label.startswith('hf-shadow'):
            assert data['shadowStorage']['liveDtypes'] == ['torch.float16']
            assert data['shadowStorage']['shadowDtypes'] == ['torch.float32']
            assert data['shadowStorage']['shadowParameterBytes'] == 2 * data['shadowStorage']['liveParameterBytes']
        for case in data['cases']:
            assert len(case['seconds']) == len(case['refreshSeconds']) == len(case['decodeSeconds']) == 5
            assert case['repeatTokensEqual'], path
            assert len(case['tokens']) == case['sequences']
            assert all(len(tokens) == 32 for tokens in case['tokens'])
            assert case['generatedTokensPerRepeat'] == 32 * case['sequences']
            assert all(abs(total - refresh - decode) < 1e-9 for total, refresh, decode in
                       zip(case['seconds'], case['refreshSeconds'], case['decodeSeconds'], strict=True))
            computed = case['generatedTokensPerRepeat'] / statistics.median(case['seconds'])
            assert abs(computed - case['tokensPerSecondTotal']) < 1e-9
        summary['inputs'][path.relative_to(HERE).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
        documents[label] = data
    for label, data in documents.items():
        for case in data['cases']:
            batch = case['sequences']
            control = next(c for c in baseline['cases'] if c['sequences'] == batch)
            throughput = case['generatedTokensPerRepeat'] / statistics.median(case['seconds'])
            baseline_throughput = control['generatedTokensPerRepeat'] / statistics.median(control['seconds'])
            summary['comparisons'].append({
                'model': model, 'variant': label, 'batch': batch, 'tokensPerSecond': throughput,
                'baselineTokensPerSecond': baseline_throughput, 'ratioToFullBatchShadow': throughput / baseline_throughput,
                'spreadPercent': 100 * (max(case['seconds']) - min(case['seconds'])) / statistics.median(case['seconds']),
                'medianRefreshMs': 1000 * statistics.median(case['refreshSeconds']),
                'decodeOnlyTokensPerSecond': case['decodeOnlyTokensPerSecondTotal'],
                'allocatedPeakMiBIncludingWarmup': case['peakAllocatedBytesIncludingWarmup'] / 2**20,
                'reservedPeakMiBIncludingWarmup': case['peakReservedBytesIncludingWarmup'] / 2**20,
                'tokensEqualShadow': case['tokens'] == control['tokens'],
                'tokensEqualOwnSingles': case['tokensEqualSingles'],
                'fullTokenStreamSha256': hashlib.sha256(json.dumps(case['tokens'], separators=(',', ':')).encode()).hexdigest(),
            })
with destination.open('x') as stream:
    json.dump(summary, stream, indent=2)
    stream.write('\n')
for row in summary['comparisons']:
    print(f"{row['model']:5} {row['variant']:19} B{row['batch']:2} {row['tokensPerSecond']:8.1f} tok/s "
          f"{row['ratioToFullBatchShadow']:5.3f}x spread={row['spreadPercent']:4.1f}% "
          f"peak={row['allocatedPeakMiBIncludingWarmup']:5.0f} MiB tokensEqualShadow={row['tokensEqualShadow']}")
