"""Whole-generation ABBA: original vs split strict attention in the selected B22 decoder (tokens must match)."""
import argparse, hashlib, importlib.util, json, os, statistics, time
from pathlib import Path
p = argparse.ArgumentParser(); p.add_argument('--gpu', action='store_true'); p.add_argument('--out', type=Path, required=True)
p.add_argument('--model', default='qwen'); p.add_argument('--samples', type=int, default=5)
a = p.parse_args()
if not a.gpu or os.environ.get('HETEROES_GPU_ACCEPTANCE') != '1' or a.out.exists(): p.error('GPU opt-in/fresh output required')
import torch
from heteroes.eval import strict_cuda
from heteroes.eval.integer_decoder import IntegerDecoderGraph
from heteroes.v3.model import load, file_manifest
def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m
bench = module('benchmark', 'runtime/scripts/benchmark_inference.py')
probe = module('probe', 'runtime/scripts/probe_strict_backend.py')
path = Path('/home/pc5070ti/projects/heteroes/.scratch/strict-integer-20261025/models') / a.model
files = file_manifest(path)
model, tok = load(path, files, 'cuda')
engines = {}
for entry in ('strict_attention', 'strict_attention_split'):
    engines[entry] = IntegerDecoderGraph(model, magnitude_bits=22, max_context=512, max_graph_bytes=6 * 1024**3)
    engines[entry].kernels._attention_entry = entry  # instance attribute: graphs capture the launch it selects
assert engines['strict_attention'].kernels is not engines['strict_attention_split'].kernels
assert 'strict_attention_split' not in vars(engines['strict_attention'].kernels).values()
short = [tok(t)['input_ids'] for t in probe.PROMPTS]
workload = Path('docs/evidence/2026-10-26-vllm-impact/workload-chat-01.json')
chat = json.loads(workload.read_text())['models'][a.model]['rows'] if a.model in json.loads(workload.read_text())['models'] else None
cases = [('short32', 32, [short[i % 8] for i in range(32)])]
if chat: cases.append(('chat128', 128, [r['tokenIds'] for r in chat[:32]]))
report = {'gpu': torch.cuda.get_device_name(), 'model': a.model, 'modelFiles': files,
          'sourceSha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
          'strictCudaSha256': hashlib.sha256(Path('runtime/src/heteroes/eval/strict_cuda.py').read_bytes()).hexdigest(),
          'cases': []}
for label, tokens, rows in cases:
    runs = {e: bench.decoder_run(engine, pad=tok.pad_token_id or 0, tokens=tokens) for e, engine in engines.items()}
    outputs = {e: r(rows) for e, r in runs.items()}
    assert outputs['strict_attention'] == outputs['strict_attention_split'], label
    times = {e: [] for e in runs}
    for s in range(a.samples):
        order = list(runs) if s % 2 == 0 else list(reversed(runs))
        for e in order + order[::-1]:
            torch.cuda.synchronize(); t = time.perf_counter(); out = runs[e](rows); torch.cuda.synchronize()
            times[e].append(time.perf_counter() - t)
            assert out == outputs[e]
    med = {e: statistics.median(v) for e, v in times.items()}
    tps = {e: 32 * tokens / m for e, m in med.items()}
    case = {'case': label, 'batch': 32, 'outputTokens': tokens, 'secondsSamples': times, 'medianTokensPerSecond': tps,
            'ratio': med['strict_attention'] / med['strict_attention_split'], 'tokensEqual': True,
            'tokensSha256': hashlib.sha256(json.dumps(outputs['strict_attention']).encode()).hexdigest()}
    report['cases'].append(case)
    print(a.model, label, {e: round(v, 1) for e, v in tps.items()}, 'ratio', round(case['ratio'], 3), flush=True)
report['status'] = 'ok'
with a.out.open('x') as f: json.dump(report, f, indent=2); f.write('\n')
