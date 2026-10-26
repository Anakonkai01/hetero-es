"""Per-kernel durations of one captured decode step (the last of a generation), in launch order."""
import argparse, importlib.util, json, os
from pathlib import Path
p = argparse.ArgumentParser(); p.add_argument('--gpu', action='store_true'); p.add_argument('--model', default='qwen')
p.add_argument('--tokens', type=int, default=8); p.add_argument('--chat', action='store_true'); p.add_argument('--out', type=Path)
a = p.parse_args()
assert a.gpu and os.environ.get('HETEROES_GPU_ACCEPTANCE') == '1'
import torch
from torch.profiler import profile, ProfilerActivity
from heteroes.eval.integer_decoder import IntegerDecoderGraph
from heteroes.v3.model import load, file_manifest
def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m
bench = module('benchmark', 'runtime/scripts/benchmark_inference.py'); probe = module('probe', 'runtime/scripts/probe_strict_backend.py')
path = Path('/home/pc5070ti/projects/heteroes/.scratch/strict-integer-20261025/models') / a.model
model, tok = load(path, file_manifest(path), 'cuda')
engine = IntegerDecoderGraph(model, magnitude_bits=22, max_context=512, max_graph_bytes=6 * 1024**3)
if a.chat:
    rows = [r['tokenIds'] for r in json.loads(Path('docs/evidence/2026-10-26-vllm-impact/workload-chat-01.json').read_text())['models'][a.model]['rows'][:32]]
else:
    short = [tok(t)['input_ids'] for t in probe.PROMPTS]; rows = [short[i % 8] for i in range(32)]
run = bench.decoder_run(engine, pad=tok.pad_token_id or 0, tokens=a.tokens)
run(rows); run(rows)
with profile(activities=[ProfilerActivity.CUDA]) as prof:
    run(rows); torch.cuda.synchronize()
ev = sorted((e.time_range.start, e.time_range.end, e.name) for e in prof.events() if e.device_type == torch.autograd.DeviceType.CUDA)
starts = [i for i, e in enumerate(ev) if e[2] == 'decode_layout']
s, t = starts[-2], starts[-1]
step = ev[s:t]
total = (step[-1][1] - step[0][0]) / 1e3
busy = sum(e - b for b, e, _ in step) / 1e3
print(f'step kernels {len(step)} span {total*1e3:.0f} us busy {busy*1e3:.0f} us')
agg = {}
for i, (b, e, n) in enumerate(step):
    gap = (b - step[i-1][1]) if i else 0
    agg.setdefault(n, [0, 0.0, 0.0]); agg[n][0] += 1; agg[n][1] += (e - b); agg[n][2] += gap
for n, (c, d, g) in sorted(agg.items(), key=lambda kv: -kv[1][1]):
    print(f'{d:8.1f} us {c:4d}x  gaps-before {g:7.1f} us  {n[:60]}')
print('layer 1 sequence:')
layer = [e for e in step]
# print the first ~25 kernels (layer 0) with durations
for b, e, n in step[:24]:
    print(f'   {e-b:7.1f} us  {n[:50]}')
print('tail:')
for b, e, n in step[-6:]:
    print(f'   {e-b:7.1f} us  {n[:50]}')
if a.out:
    a.out.write_text(json.dumps([[b, e, n] for b, e, n in step]))
