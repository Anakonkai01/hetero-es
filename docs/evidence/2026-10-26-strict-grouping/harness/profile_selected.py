"""External CUDA graph event scopes: diagnostic attribution, not an uninstrumented throughput result."""
import argparse
from collections import defaultdict
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import statistics

p = argparse.ArgumentParser()
p.add_argument('--gpu', action='store_true')
p.add_argument('--out', type=Path, required=True)
a = p.parse_args()
if not a.gpu or os.environ.get('HETEROES_GPU_ACCEPTANCE') != '1' or a.out.exists():
    p.error('GPU opt-in and fresh output required')
import torch
from heteroes.eval.integer_decoder import IntegerDecoderGraph
from heteroes.v3.model import load, file_manifest

spec = importlib.util.spec_from_file_location('benchmark', 'runtime/scripts/benchmark_inference.py')
bench = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bench)
spec = importlib.util.spec_from_file_location('probe', 'runtime/scripts/probe_strict_backend.py')
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)
path = Path('/home/pc5070ti/projects/heteroes/.scratch/strict-integer-20261025/models/qwen')
files = file_manifest(path)
model, tokenizer = load(path, files, 'cuda')
engine = IntegerDecoderGraph(model, magnitude_bits=22, max_context=512, max_graph_bytes=4*1024**3)
names = {id(module): name for name, module in model.named_modules()}
scopes = []

def wrapped(call, label):
    def invoke(*items, **kwargs):
        if not torch.cuda.is_current_stream_capturing():
            return call(*items, **kwargs)
        begin = torch.cuda.Event(enable_timing=True, external=True)
        end = torch.cuda.Event(enable_timing=True, external=True)
        begin.record()
        result = call(*items, **kwargs)
        end.record()
        scopes.append((label(*items), begin, end))
        return result
    return invoke

engine._decode_project = wrapped(engine._decode_project, lambda value, module, flag: names[id(module)])
engine._decode_project_many = wrapped(engine._decode_project_many,
    lambda value, modules, flag: names[id(modules[0])].rsplit('.', 1)[0] + '.group')
engine.kernels.attention_packed = wrapped(engine.kernels.attention_packed, lambda *items: 'attention')
engine._decode_core = wrapped(engine._decode_core, lambda state: 'total')
prompts = [tokenizer(text)['input_ids'] for text in probe.PROMPTS]
selected = [prompts[i % 8] for i in range(32)]
run = bench.decoder_run(engine, pad=tokenizer.pad_token_id or 0, tokens=32)
expected = run(selected)
assert engine._session.capture_count == 1 and scopes
samples = defaultdict(list)
for repeat in range(10):
    assert run(selected) == expected
    torch.cuda.synchronize()
    current = {}
    for name, begin, end in scopes:
        elapsed = begin.elapsed_time(end)
        assert elapsed > 0
        current[name] = current.get(name, 0.0) + elapsed
    assert sum(v for k, v in current.items() if k != 'total') < current['total']
    for name, value in current.items():
        samples[name].append(value)
median = {name: statistics.median(values) for name, values in samples.items()}
report = {'status': 'ok', 'sourceSha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
          'gpu': torch.cuda.get_device_name(), 'modelFiles': files, 'samplesMs': dict(samples),
          'medianMs': median, 'kernelIdentity': engine.kernel_identity(),
          'scope': 'One final captured decode step per repeat, batch32/context512/32 outputs. '
                   'External event nodes perturb scheduling. No throughput or universal attribution claim.'}
with a.out.open('x') as f:
    json.dump(report, f, indent=2)
    f.write('\n')
for name, value in sorted(median.items(), key=lambda item: item[1], reverse=True)[:15]:
    print(name, value, value / median['total'], flush=True)
