"""Whole-generation ABBA: selected tile projections vs streamed projections in the B22 decoder (tokens must match)."""
import argparse, hashlib, importlib.util, json, os, statistics, time
from pathlib import Path
p = argparse.ArgumentParser(); p.add_argument('--gpu', action='store_true'); p.add_argument('--out', type=Path, required=True)
p.add_argument('--model', default='qwen'); p.add_argument('--samples', type=int, default=5)
p.add_argument('--batch', type=int, default=32)
p.add_argument('--models-root', default='/home/pc5070ti/projects/heteroes/.scratch/strict-integer-20261025/models')
p.add_argument('--benchmark', default='runtime/scripts/benchmark_inference.py'); p.add_argument('--probe', default='runtime/scripts/probe_strict_backend.py')
p.add_argument('--workload', default='docs/evidence/2026-10-26-vllm-impact/workload-chat-01.json')
p.add_argument('--integer-cuda', default='runtime/src/heteroes/eval/integer_cuda.py')
a = p.parse_args()
if not a.gpu or os.environ.get('HETEROES_GPU_ACCEPTANCE') != '1' or a.out.exists(): p.error('GPU opt-in/fresh output required')
import torch
from heteroes.eval.integer_decoder import IntegerDecoderGraph
from heteroes.v3.model import load, file_manifest
def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m
bench = module('benchmark', a.benchmark)
probe = module('probe', a.probe)
path = Path(a.models_root) / a.model
files = file_manifest(path)
model, tok = load(path, files, 'cuda')
engines = {s: IntegerDecoderGraph(model, magnitude_bits=22, max_context=512, max_graph_bytes=6 * 1024**3, mma_schedule=s)
           for s in ('tile', 'stream')}
short = [tok(t)['input_ids'] for t in probe.PROMPTS]
models = json.loads(Path(a.workload).read_text())['models']
chat = models[a.model]['rows'] if a.model in models else None
B = a.batch
cases = [('short32', 32, [short[i % 8] for i in range(B)])]
if chat: cases.append(('chat128', 128, [r['tokenIds'] for r in chat[:B]]))
report = {'gpu': torch.cuda.get_device_name(), 'torch': torch.__version__, 'model': a.model, 'modelFiles': files, 'batch': B,
          'sourceSha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
          'integerCudaSha256': hashlib.sha256(Path(a.integer_cuda).read_bytes()).hexdigest(),
          'fingerprints': {s: e.fingerprint for s, e in engines.items()}, 'cases': []}
for label, tokens, rows in cases:
    runs = {s: bench.decoder_run(engine, pad=tok.pad_token_id or 0, tokens=tokens) for s, engine in engines.items()}
    outputs = {s: r(rows) for s, r in runs.items()}
    assert outputs['tile'] == outputs['stream'], label
    times = {s: [] for s in runs}
    for i in range(a.samples):
        order = list(runs) if i % 2 == 0 else list(reversed(runs))
        for s in order + order[::-1]:
            torch.cuda.synchronize(); t = time.perf_counter(); out = runs[s](rows); torch.cuda.synchronize()
            times[s].append(time.perf_counter() - t)
            assert out == outputs[s]
    med = {s: statistics.median(v) for s, v in times.items()}
    tps = {s: B * tokens / m for s, m in med.items()}
    case = {'case': label, 'batch': B, 'outputTokens': tokens, 'secondsSamples': times, 'medianTokensPerSecond': tps,
            'ratio': med['tile'] / med['stream'], 'tokensEqual': True,
            'tokensSha256': hashlib.sha256(json.dumps(outputs['tile']).encode()).hexdigest()}
    report['cases'].append(case)
    print(a.model, label, 'B', B, {s: round(v, 1) for s, v in tps.items()}, 'ratio', round(case['ratio'], 3), flush=True)
report['status'] = 'ok'
with a.out.open('x') as f: json.dump(report, f, indent=2); f.write('\n')
