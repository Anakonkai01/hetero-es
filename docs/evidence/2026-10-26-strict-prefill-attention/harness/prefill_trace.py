"""Kernel aggregates and host gaps of one prefill (generation of 1 token) for short and chat workloads."""
import argparse, importlib.util, json, os, time
from pathlib import Path
p = argparse.ArgumentParser(); p.add_argument('--gpu', action='store_true'); p.add_argument('--chat', action='store_true')
a = p.parse_args()
if not a.gpu or os.environ.get('HETEROES_GPU_ACCEPTANCE') != '1': p.error('Explicit GPU opt-in required')
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
run = bench.decoder_run(engine, pad=tok.pad_token_id or 0, tokens=1)
run(rows); run(rows)
torch.cuda.synchronize(); t = time.perf_counter(); run(rows); torch.cuda.synchronize(); print('plain ms', (time.perf_counter() - t) * 1e3)
with profile(activities=[ProfilerActivity.CUDA, ProfilerActivity.CPU]) as prof:
    run(rows); torch.cuda.synchronize()
ev = sorted((e.time_range.start, e.time_range.end, e.name) for e in prof.events() if e.device_type == torch.autograd.DeviceType.CUDA)
span = (ev[-1][1] - ev[0][0]) / 1e3
gaps = []
last = ev[0][1]
for b, e, n in ev[1:]:
    if b > last: gaps.append((b - last, n))
    last = max(last, e)
print(f'span {span:.1f} ms kernels {len(ev)} idle {sum(g for g, _ in gaps)/1e3:.1f} ms')
agg = {}
for g, n in gaps: agg[n] = agg.get(n, 0) + g
big = []
last = ev[0][1]
for k, (b, e, n) in enumerate(ev[1:], 1):
    if b - last > 150: big.append((round((b - last) / 1e3, 2), k, n[:50], ev[k - 1][2][:40]))
    last = max(last, e)
print('big gaps (ms, index, next, previous):'); [print('  ', g) for g in big[:20]]
print('idle before (top):', [(n[:40], round(v / 1e3, 2)) for n, v in sorted(agg.items(), key=lambda kv: -kv[1])[:8]])
by = {}
for b, e, n in ev: by.setdefault(n, [0, 0.0]); by[n][0] += 1; by[n][1] += (e - b) / 1e3
for n, (c, ms) in sorted(by.items(), key=lambda kv: -kv[1][1])[:14]: print(f'  {ms:7.2f} ms {c:5d}x {n[:70]}')
# CPU-side: time spent before the first kernel and between
cpu = [e for e in prof.events() if e.device_type == torch.autograd.DeviceType.CPU]
import cProfile, pstats, io
pr = cProfile.Profile(); torch.cuda.synchronize(); pr.enable(); run(rows); torch.cuda.synchronize(); pr.disable()
s = io.StringIO(); pstats.Stats(pr, stream=s).sort_stats('cumulative').print_stats(40); print(s.getvalue()[:6000])
