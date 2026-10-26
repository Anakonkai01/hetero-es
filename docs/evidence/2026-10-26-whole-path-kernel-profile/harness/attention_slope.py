"""Per-step strict_attention kernel durations (CUPTI) for B22 chat128 batch 32."""
import importlib.util, json, os, statistics, sys
from pathlib import Path
assert os.environ.get('HETEROES_GPU_ACCEPTANCE') == '1' and '--gpu' in sys.argv
import torch
from torch.profiler import profile, ProfilerActivity
from heteroes.eval.integer_decoder import IntegerDecoderGraph
from heteroes.v3.model import load, file_manifest
def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m
bench = module('benchmark', 'runtime/scripts/benchmark_inference.py')
path = Path('/home/pc5070ti/projects/heteroes/.scratch/strict-integer-20261025/models/qwen')
model, tok = load(path, file_manifest(path), 'cuda')
engine = IntegerDecoderGraph(model, magnitude_bits=22, max_context=512, max_graph_bytes=6 * 1024**3)
rows = [r['tokenIds'] for r in json.loads(Path('docs/evidence/2026-10-26-vllm-impact/workload-chat-01.json').read_text())['models']['qwen']['rows'][:32]]
print('prompt lengths min/max', min(map(len, rows)), max(map(len, rows)))
run = bench.decoder_run(engine, pad=tok.pad_token_id or 0, tokens=128)
run(rows); torch.cuda.synchronize()
with profile(activities=[ProfilerActivity.CUDA]) as prof:
    run(rows); torch.cuda.synchronize()
att = sorted((e.time_range.start, e.time_range.end) for e in prof.events() if e.name == 'strict_attention')
d = [(e - s) for s, e in att]
per_step = [sum(d[i:i + 24]) for i in range(0, len(d), 24)]
print('calls', len(d), 'steps', len(per_step))
for i in (0, 1, 2, 16, 32, 64, 96, 127):
    print(f'step {i:3d}: attention {per_step[i]/1e3:.3f} ms/step ({per_step[i]/24:.1f} us/layer)')
