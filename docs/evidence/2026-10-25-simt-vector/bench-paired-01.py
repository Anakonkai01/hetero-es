"""Same-process ABBA with one FP16 model and isolated compiled-function caches per source variant."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import statistics
from types import SimpleNamespace

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--gpu', action='store_true')
parser.add_argument('--model-path', type=Path, required=True)
parser.add_argument('--candidate-source', type=Path, required=True)
parser.add_argument('--out', type=Path, required=True)
args = parser.parse_args()
if not args.gpu or os.environ.get('HETEROES_GPU_ACCEPTANCE') != '1' or args.out.exists():
    parser.error('GPU opt-in and fresh evidence path are required')
import torch
from heteroes.eval import integer_cuda as ic

spec = importlib.util.spec_from_file_location('integer_candidate', args.candidate_source)
candidate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(candidate)
sources = {'old': ic._SOURCE, 'new': candidate._SOURCE}
spec = importlib.util.spec_from_file_location('benchmark', Path('runtime/scripts/benchmark_inference.py'))
bench = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bench)
report = {
    'status': 'running', 'hardwareQualified': False, 'selected': False,
    'baselineNumericCommit': '3fd704a5',
    'probeSha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    'cudaSourceSha256': {label: hashlib.sha256(source.encode()).hexdigest() for label, source in sources.items()},
    'environment': {}, 'cases': [],
    'limits': 'Runtime source and function-cache overrides, same model/process, ABBA, six timed observations per variant. Unisolated GPU. Full outputs and final logits must match. No selected backend, managed/native/general-quality qualification.',
}
try:
    options = SimpleNamespace(model_path=args.model_path, engine='strict-integer', integer_bits=22,
                              max_context=512, max_new_tokens=32, graph_max_bytes=4 * 1024**3)
    engine, prompts, run = bench.load_engine(options, report)
    kernels = engine.kernels
    caches = {'old': kernels._functions, 'new': {}}
    builds = {'old': kernels._builds, 'new': {}}
    for batch in (1, 8, 32):
        rows = [prompts[i % len(prompts)] for i in range(batch)]
        observations, golden = [], None
        for variant in ('old', 'new', 'new', 'old'):
            engine.release_graph()
            ic._SOURCE = sources[variant]
            kernels._functions, kernels._builds = caches[variant], builds[variant]
            torch.cuda.reset_peak_memory_stats()
            case = bench.measure(run, rows, 32, 3, torch.cuda.synchronize)
            logits = hashlib.sha256(engine._session.last_logits.detach().cpu().contiguous().numpy().tobytes()).hexdigest()
            if golden is None:
                golden = (case['tokens'], logits)
            assert golden == (case['tokens'], logits) and case['repeatTokensEqual'], (batch, variant)
            case.update(variant=variant, lastLogitsSha256=logits, peakAllocatedBytes=torch.cuda.max_memory_allocated())
            observations.append(case)
        summaries = {}
        for variant in ('old', 'new'):
            seconds = [s for case in observations if case['variant'] == variant for s in case['seconds']]
            summaries[variant] = {'seconds': seconds, 'medianSeconds': statistics.median(seconds),
                                  'tokensPerSecondTotal': batch * 32 / statistics.median(seconds)}
        ratio = summaries['new']['tokensPerSecondTotal'] / summaries['old']['tokensPerSecondTotal']
        report['cases'].append({'batch': batch, 'observations': observations, 'summary': summaries,
                                'ratio': ratio, 'tokensAndFinalLogitsEqual': True})
        print(json.dumps({'batch': batch, 'old': summaries['old']['tokensPerSecondTotal'],
                          'new': summaries['new']['tokensPerSecondTotal'], 'ratio': ratio}), flush=True)
    engine.release_graph()
    report['buildsByVariant'] = builds
    report['status'] = 'ok'
except Exception as exc:
    report.update(status='error', errorType=type(exc).__name__, error=str(exc))
finally:
    ic._SOURCE = sources['old']
with args.out.open('x') as f:
    json.dump(report, f, indent=2)
    f.write('\n')
print(json.dumps({'status': report['status'], 'error': report.get('error')}), flush=True)
raise SystemExit(report['status'] != 'ok')
