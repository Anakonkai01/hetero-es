"""Opt-in finite CUDA activity profile of common decoder layouts, independent of a checkpoint."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import statistics
import time

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--out', type=Path, required=True)
p.add_argument('--gpu', action='store_true')
a = p.parse_args()
if not a.gpu or os.environ.get('HETEROES_GPU_ACCEPTANCE') != '1' or a.out.exists():
    p.error('Need GPU acceptance and a new receipt')
import torch
from transformers import LlamaConfig, LlamaForCausalLM, MistralConfig, MistralForCausalLM, Qwen2Config, Qwen2ForCausalLM
from heteroes.eval.strict_decoder_packed import StrictDecoderPacked

report = {'status': 'running', 'hardwareQualified': False, 'gpu': torch.cuda.get_device_name(),
          'sourceSha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), 'cases': [],
          'limits': 'One-layer randomly initialized graph fixtures, not trained checkpoints or serving/ES acceptance. '
                    'Profiler adds overhead; non-profiled wall medians are recorded separately.'}
try:
    for cfg, cls, hidden, intermediate, heads, kv in (
        (Qwen2Config, Qwen2ForCausalLM, 512, 1536, 8, 2),
        (LlamaConfig, LlamaForCausalLM, 1024, 2816, 16, 4),
        (MistralConfig, MistralForCausalLM, 1536, 4096, 24, 8),
    ):
        torch.manual_seed(71)
        model = cls(cfg(hidden_size=hidden, intermediate_size=intermediate, num_attention_heads=heads,
                        num_key_value_heads=kv, num_hidden_layers=1, vocab_size=32768,
                        max_position_embeddings=256, sliding_window=None, tie_word_embeddings=False)).half().eval().cuda()
        engine = StrictDecoderPacked(model, max_context=256, allow_fixture=True)
        for batch in (1, 8, 32):
            rows = [torch.tensor([[2, 5, 7, 11] * 8], device='cuda') for _ in range(batch)]
            _, cache = engine.forward_batch(rows)
            tails = [r[:, -1:] for r in rows]
            for _ in range(2):
                engine.forward_batch(tails, cache)
            durations = []
            for _ in range(3):
                torch.cuda.synchronize(); start = time.perf_counter()
                engine.forward_batch(tails, cache)
                torch.cuda.synchronize(); durations.append(time.perf_counter() - start)
            with torch.profiler.profile(activities=[torch.profiler.ProfilerActivity.CPU, torch.profiler.ProfilerActivity.CUDA]) as prof:
                engine.forward_batch(tails, cache)
                torch.cuda.synchronize()
            cuda = {}
            for event in prof.events():
                if str(event.device_type) == 'DeviceType.CUDA':
                    item = cuda.setdefault(event.name, {'calls': 0, 'totalUs': 0})
                    item['calls'] += 1; item['totalUs'] += event.time_range.elapsed_us()
            report['cases'].append({'family': model.config.model_type, 'hidden': hidden, 'intermediate': intermediate,
                                    'batch': batch, 'seconds': durations, 'medianSeconds': statistics.median(durations),
                                    'cuda': sorted([dict(name=n, **v) for n, v in cuda.items()], key=lambda x: -x['totalUs']),
                                    'kernelIdentity': engine.kernel_identity()})
        del engine, model, cache
        torch.cuda.empty_cache()
    report['status'] = 'ok'
except Exception as exc:
    report.update(status='error', errorType=type(exc).__name__, error=str(exc))
with a.out.open('x') as f:
    json.dump(report, f, indent=2); f.write('\n')
print(json.dumps({'status': report['status'], 'cases': len(report['cases']), 'error': report.get('error')}))
raise SystemExit(report['status'] != 'ok')
