"""CUPTI kernel trace of whole B22 / vendor-FP16 generations; no timing nodes inside the graph."""
import argparse
from collections import defaultdict
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import time

p = argparse.ArgumentParser()
p.add_argument('--gpu', action='store_true')
p.add_argument('--out', type=Path, required=True)
a = p.parse_args()
if not a.gpu or os.environ.get('HETEROES_GPU_ACCEPTANCE') != '1' or a.out.exists():
    p.error('GPU opt-in/fresh output required')
import torch
from torch.profiler import profile, ProfilerActivity
from heteroes.eval.integer_decoder import IntegerDecoderGraph
from heteroes.eval.fp16_decoder import Fp16DecoderGraph
from heteroes.v3.model import load, file_manifest


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


bench = module('benchmark', 'runtime/scripts/benchmark_inference.py')
probe = module('probe', 'runtime/scripts/probe_strict_backend.py')
path = Path('/home/pc5070ti/projects/heteroes/.scratch/strict-integer-20261025/models/qwen')
files = file_manifest(path)
model, tokenizer = load(path, files, 'cuda')
engines = {'b22': lambda: IntegerDecoderGraph(model, magnitude_bits=22, max_context=512, max_graph_bytes=6 * 1024**3),
           'fp16': lambda: Fp16DecoderGraph(model, max_context=512, max_graph_bytes=6 * 1024**3)}
short = [tokenizer(text)['input_ids'] for text in probe.PROMPTS]
workload = Path('docs/evidence/2026-10-26-vllm-impact/workload-chat-01.json')
chat = json.loads(workload.read_text())['models']['qwen']['rows']
report = {'gpu': torch.cuda.get_device_name(), 'torch': torch.__version__, 'modelFiles': files,
          'sourceSha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
          'workloadSha256': hashlib.sha256(workload.read_bytes()).hexdigest(), 'cases': [],
          'limits': 'One traced generation per case after warmup; CUPTI tracing may add small overhead; '
                    'vendor FP16 is a different-arithmetic control.'}
for own, make in engines.items():
    engine = make()
    for label, tokens, rows in [('short32', 32, [short[i % 8] for i in range(32)]),
                                ('chat128', 128, [r['tokenIds'] for r in chat[:32]])]:
        run = bench.decoder_run(engine, pad=tokenizer.pad_token_id or 0, tokens=tokens)
        expected = run(rows)
        assert run(rows) == expected
        torch.cuda.synchronize()
        begin = time.perf_counter()
        run(rows)
        torch.cuda.synchronize()
        plain = time.perf_counter() - begin
        with profile(activities=[ProfilerActivity.CPU, ProfilerActivity.CUDA]) as prof:
            got = run(rows)
            torch.cuda.synchronize()
        assert got == expected
        kernels = [e for e in prof.events() if e.device_type == torch.autograd.DeviceType.CUDA]
        spans = sorted((e.time_range.start, e.time_range.end, e.name) for e in kernels)
        wall = (spans[-1][1] - spans[0][0]) / 1e3
        busy = 0.0
        last = None
        for s, e, _ in spans:
            if last is None or s >= last:
                busy += e - s
                last = e
            elif e > last:
                busy += e - last
                last = e
        by = defaultdict(lambda: [0, 0.0])
        for s, e, n in spans:
            by[n][0] += 1
            by[n][1] += (e - s) / 1e3
        top = sorted(by.items(), key=lambda kv: -kv[1][1])
        case = {'engine': own, 'case': label, 'batch': 32, 'outputTokens': tokens,
                'plainSeconds': plain, 'plainTokensPerSecond': 32 * tokens / plain,
                'gpuSpanMs': wall, 'gpuBusyMs': busy / 1e3, 'kernelCount': len(spans),
                'kernels': [{'name': n[:160], 'count': c, 'ms': ms} for n, (c, ms) in top]}
        report['cases'].append(case)
        print(own, label, f"plain {case['plainTokensPerSecond']:.0f} tok/s span {wall:.1f}ms busy {busy/1e3:.1f}ms "
              f"kernels {len(spans)}", flush=True)
        for k in case['kernels'][:14]:
            print(f"   {k['ms']:8.2f} ms {k['count']:6d}x  {k['name'][:110]}", flush=True)
    del engine
    torch.cuda.empty_cache()
report['status'] = 'ok'
with a.out.open('x') as f:
    json.dump(report, f, indent=2)
    f.write('\n')
