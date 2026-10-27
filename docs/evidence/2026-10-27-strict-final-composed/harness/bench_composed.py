"""Final bounded performance round: TMA host-map prefill + request-sized KV + ordered K/V stages, composed.

One engine per process. `--variant baseline` is the selected 0eb86cb9 decoder; `--variant composed` applies the three
unselected helpers unchanged from their sealed evidence folders. Run baseline/composed/baseline/composed as separate
processes (ABAB) on an idle GPU. Same prompts, token counts, context bound, EOS and prefix policy as earlier pilots."""
import argparse, hashlib, importlib.util, json, os, statistics, sys, time
from pathlib import Path

EVIDENCE = Path(__file__).resolve().parents[2]
HELPERS = [EVIDENCE / '2026-10-27-strict-tma-host-maps/harness', EVIDENCE / '2026-10-27-strict-request-cache-context/harness',
           EVIDENCE / '2026-10-27-strict-attention-key-stages/harness']
p = argparse.ArgumentParser(); p.add_argument('--gpu', action='store_true'); p.add_argument('--out', type=Path, required=True)
p.add_argument('--variant', choices=('baseline', 'composed', 'bucket-stage'), required=True); p.add_argument('--key-tile', type=int, default=128)
p.add_argument('--model', default='qwen'); p.add_argument('--samples', type=int, default=5)
p.add_argument('--models-root', default='/home/pc5070ti/projects/heteroes/.scratch/strict-integer-20261025/models')
p.add_argument('--benchmark', default='runtime/scripts/benchmark_inference.py'); p.add_argument('--probe', default='runtime/scripts/probe_strict_backend.py')
p.add_argument('--workload', default='docs/evidence/2026-10-26-vllm-impact/workload-chat-01.json')
a = p.parse_args()
if not a.gpu or os.environ.get('HETEROES_GPU_ACCEPTANCE') != '1' or a.out.exists(): p.error('GPU opt-in/fresh output required')
sys.path[:0] = [str(h) for h in HELPERS]
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
transport = None
if a.variant == 'baseline':
    engine = IntegerDecoderGraph(model, magnitude_bits=22, max_context=512, max_graph_bytes=6 * 1024**3)
else:
    from bucket import BucketGraph
    from stages import KeyStageKernels
    engine = BucketGraph(model, magnitude_bits=22, max_context=512, max_graph_bytes=6 * 1024**3)
    from heteroes.eval.integer_cuda import IntegerCudaKernels
    assert type(engine.kernels) is IntegerCudaKernels
    engine.kernels.__class__ = KeyStageKernels; engine.kernels.key_tile = a.key_tile
    if a.variant == 'composed':
        from prefill import PrefillTransport
        transport = PrefillTransport(engine.kernels, minimum_work=0)
short = [tok(t)['input_ids'] for t in probe.PROMPTS]
models = json.loads(Path(a.workload).read_text())['models']
cases = [('short32', 32, [short[i % 8] for i in range(32)]), ('chat128', 128, [r['tokenIds'] for r in models[a.model]['rows'][:32]])]
src = Path(heteroes.__file__).parent
helper_hashes = {str(q.relative_to(EVIDENCE)): hashlib.sha256(q.read_bytes()).hexdigest() for h in HELPERS for q in sorted(h.glob('*.py'))}
report = {'label': a.out.stem, 'variant': a.variant, 'keyTile': a.key_tile, 'gpu': torch.cuda.get_device_name(), 'model': a.model,
          'modelFiles': files, 'sourceRoot': str(src), 'fingerprint': engine.fingerprint,
          'runtimeSha256': {f: hashlib.sha256((src / f).read_bytes()).hexdigest() for f in ('eval/integer_cuda.py', 'eval/strict_cuda.py', 'eval/strict_decoder_graph.py', 'eval/integer_decoder.py')},
          'harnessSha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), 'helperSha256': helper_hashes, 'cases': []}
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
    print(a.out.stem, label, round(32 * tokens / med, 1), report['cases'][-1]['tokensSha256'][:12], flush=True)
report['tma'] = None if transport is None else {'encoded': transport.map_cache.encoded, 'patched': transport.map_cache.patched, 'projectionCalls': transport.calls}
report['limits'] = 'Research composition of unselected helpers; not runtime source. Synchronized whole generations, no EOS stopping or prefix reuse.'
with a.out.open('x') as f: json.dump(report, f, indent=2); f.write('\n')
