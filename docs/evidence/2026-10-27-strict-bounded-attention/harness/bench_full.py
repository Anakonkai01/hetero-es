"""One engine per process (default B22 decoder of whatever source is on PYTHONPATH); repeated runs, tokens hashed.

Run alternately with the baseline and the new source tree (ABAB processes) to compare whole generations."""
import argparse, hashlib, importlib.util, json, os, statistics, time
from pathlib import Path
p = argparse.ArgumentParser(); p.add_argument('--gpu', action='store_true'); p.add_argument('--out', type=Path, required=True)
p.add_argument('--model', default='qwen'); p.add_argument('--samples', type=int, default=5); p.add_argument('--label', required=True)
p.add_argument('--models-root', default='/home/pc5070ti/projects/heteroes/.scratch/strict-integer-20261025/models')
p.add_argument('--benchmark', default='runtime/scripts/benchmark_inference.py'); p.add_argument('--probe', default='runtime/scripts/probe_strict_backend.py')
p.add_argument('--workload', default='docs/evidence/2026-10-26-vllm-impact/workload-chat-01.json')
p.add_argument('--bounded-score',action='store_true')
a = p.parse_args()
if not a.gpu or os.environ.get('HETEROES_GPU_ACCEPTANCE') != '1' or a.out.exists(): p.error('GPU opt-in/fresh output required')
import torch
import heteroes
from heteroes.eval.integer_decoder import IntegerDecoderGraph
from heteroes.v3.model import load, file_manifest
def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m
bench = module('benchmark', a.benchmark); probe = module('probe', a.probe)
path = Path(a.models_root) / a.model
files = file_manifest(path)
model, tok = load(path, files, 'cuda')
engine = IntegerDecoderGraph(model, magnitude_bits=22, max_context=512, max_graph_bytes=6 * 1024**3)
from bounded import BoundedAttentionKernels
if a.bounded_score:engine.kernels.__class__=BoundedAttentionKernels
short = [tok(t)['input_ids'] for t in probe.PROMPTS]
models = json.loads(Path(a.workload).read_text())['models']
cases = [('short32', 32, [short[i % 8] for i in range(32)])]
if a.model in models: cases.append(('chat128', 128, [r['tokenIds'] for r in models[a.model]['rows'][:32]]))
src = Path(heteroes.__file__).parent
report = {'label': a.label, 'gpu': torch.cuda.get_device_name(), 'model': a.model, 'modelFiles': files,
          'sourceRoot': str(src), 'fingerprint': engine.fingerprint,
          'integerCudaSha256': hashlib.sha256((src / 'eval/integer_cuda.py').read_bytes()).hexdigest(),
          'boundedScore':a.bounded_score,'probeHashes':{q.name:hashlib.sha256(q.read_bytes()).hexdigest() for q in Path(__file__).parent.glob('*.py')},
          'decoderGraphSha256': hashlib.sha256((src / 'eval/strict_decoder_graph.py').read_bytes()).hexdigest(), 'cases': []}
for label, tokens, rows in cases:
    run = bench.decoder_run(engine, pad=tok.pad_token_id or 0, tokens=tokens)
    expected = run(rows)
    times = []
    for _ in range(a.samples):
        torch.cuda.synchronize(); t = time.perf_counter(); out = run(rows); torch.cuda.synchronize()
        times.append(time.perf_counter() - t); assert out == expected
    med = statistics.median(times)
    report['cases'].append({'case': label, 'outputTokens': tokens, 'secondsSamples': times, 'medianTokensPerSecond': 32 * tokens / med,
                            'tokensSha256': hashlib.sha256(json.dumps(expected).encode()).hexdigest()})
    print(a.label, a.model, label, round(32 * tokens / med, 1), report['cases'][-1]['tokensSha256'][:12], flush=True)
report['builds']=engine.kernels._builds
report['limits']='Unselected guarded QK score tree; identical FP32 node order, scaling and nonlinearities. Full request time includes guard overheads. No trained cross-device qualification.'
with a.out.open('x') as f: json.dump(report, f, indent=2); f.write('\n')
