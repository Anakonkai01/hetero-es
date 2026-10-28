"""Timeline of one 1-token generation: gaps by (previous, next) kernel pair and the first events."""
import argparse, importlib.util, json, os, time
from pathlib import Path
p = argparse.ArgumentParser(); p.add_argument('--gpu', action='store_true'); p.add_argument('--chat', action='store_true'); p.add_argument('--tokens', type=int, default=1)
a = p.parse_args()
assert a.gpu and os.environ.get('HETEROES_GPU_ACCEPTANCE') == '1'
import torch
from torch.profiler import profile, ProfilerActivity
from heteroes.eval.integer_decoder import IntegerDecoderGraph
from heteroes.v3.model import load, file_manifest
def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m
bench = module('benchmark', 'runtime/scripts/benchmark_inference.py'); probe = module('probe', 'runtime/scripts/probe_strict_backend.py')
path = Path('/home/pc5070ti/projects/heteroes/.scratch/strict-integer-20261025/models/qwen')
model, tok = load(path, file_manifest(path), 'cuda')
engine = IntegerDecoderGraph(model, magnitude_bits=22, max_context=512, max_graph_bytes=6 * 1024**3)
if a.chat:
    rows = [r['tokenIds'] for r in json.loads(Path('docs/evidence/2026-10-26-vllm-impact/workload-chat-01.json').read_text())['models']['qwen']['rows'][:32]]
else:
    short = [tok(t)['input_ids'] for t in probe.PROMPTS]; rows = [short[i % 8] for i in range(32)]
run = bench.decoder_run(engine, pad=tok.pad_token_id or 0, tokens=a.tokens)
run(rows); run(rows)
for _ in range(3):
    torch.cuda.synchronize(); t = time.perf_counter(); run(rows); torch.cuda.synchronize(); print('plain ms', round((time.perf_counter() - t) * 1e3, 2))
with profile(activities=[ProfilerActivity.CUDA, ProfilerActivity.CPU]) as prof:
    run(rows); torch.cuda.synchronize()
ev = sorted((e.time_range.start, e.time_range.end, e.name) for e in prof.events() if e.device_type == torch.autograd.DeviceType.CUDA)
pairs = {}; last = ev[0][1]; seq = []
for k, (b, e, n) in enumerate(ev):
    g = max(0, b - last) if k else 0
    seq.append((g, e - b, n))
    if k: pairs.setdefault((ev[k-1][2][:28], n[:28]), [0, 0.0]); pairs[(ev[k-1][2][:28], n[:28])][0] += 1; pairs[(ev[k-1][2][:28], n[:28])][1] += g
    last = max(last, e)
print('span ms', round((ev[-1][1] - ev[0][0]) / 1e3, 2), 'idle ms', round(sum(s[0] for s in seq) / 1e3, 2))
for (pv, nx), (c, g) in sorted(pairs.items(), key=lambda kv: -kv[1][1])[:25]:
    print(f'{g/1e3:7.2f} ms {c:4d}x  {pv} -> {nx}')
print('first 140 events (gap us, dur us, name):')
for g, d, n in seq[:140]: print(f'  {g:7.1f} {d:7.1f} {n[:60]}')
names = [n for _, _, n in ev]
i0 = names.index('integer_weights'); i1 = len(names) - 1 - names[::-1].index('decode_prefix')
idle = 0; last = ev[i0][1]; big = []
for b, e, n in ev[i0 + 1:i1 + 1]:
    if b > last: idle += b - last
    if b - last > 30: big.append((round((b - last)), n[:40]))
    last = max(last, e)
print('forward window ms', round((ev[i1][1] - ev[i0][0]) / 1e3, 2), 'idle ms', round(idle / 1e3, 2), 'gaps>30us', len(big), sum(g for g, _ in big))
from collections import Counter
c = Counter(n for _, n in big); print(c.most_common(10))
print('after prefix to end ms', round((ev[-1][1] - ev[i1][1]) / 1e3, 2), [n[:30] for _, _, n in ev[i1+1:i1+40]])
