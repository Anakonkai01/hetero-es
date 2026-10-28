"""Experiment: L2-prefetch the next projections' FP16 weights from a side stream while compute-bound kernels
(attention, glue) run. Timing + token hash vs. the unpatched engine. Scratch only."""
import argparse, hashlib, importlib.util, json, os, statistics, time
from pathlib import Path
p = argparse.ArgumentParser(); p.add_argument('--gpu', action='store_true'); p.add_argument('--mode', default='off')
p.add_argument('--ctas', type=int, default=6); p.add_argument('--chat', action='store_true'); p.add_argument('--tokens', type=int, default=32)
p.add_argument('--trace', action='store_true'); p.add_argument('--entry', default=''); p.add_argument('--bulk', type=int, default=0); p.add_argument('--threads', type=int, default=512)
a = p.parse_args(); assert a.gpu and os.environ.get('HETEROES_GPU_ACCEPTANCE') == '1'
import torch
from heteroes.eval.integer_decoder import IntegerDecoderGraph
from heteroes.eval import strict_cuda as sc
from heteroes.v3.model import load, file_manifest
def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m
bench = module('benchmark', 'runtime/scripts/benchmark_inference.py'); probe = module('probe', 'runtime/scripts/probe_strict_backend.py')
path = Path('/home/pc5070ti/projects/heteroes/.scratch/strict-integer-20261025/models/qwen')
model, tok = load(path, file_manifest(path), 'cuda')
engine = IntegerDecoderGraph(model, magnitude_bits=22, max_context=512, max_graph_bytes=6 * 1024**3)
K = engine.kernels
if a.entry: K._attention_entry = a.entry
SRC = r'''
extern "C" __global__ void l2_lines(const char* a, const char* b, const char* c, int na, int nb, int nc) {
  const int t = blockIdx.x * blockDim.x + threadIdx.x, T = gridDim.x * blockDim.x;
  for (int i = t; i < na; i += T) asm volatile("prefetch.global.L2 [%0];" :: "l"(a + (size_t)i * 128));
  for (int i = t; i < nb; i += T) asm volatile("prefetch.global.L2 [%0];" :: "l"(b + (size_t)i * 128));
  for (int i = t; i < nc; i += T) asm volatile("prefetch.global.L2 [%0];" :: "l"(c + (size_t)i * 128));
}
extern "C" __global__ void l2_bulk(const char* a, const char* b, const char* c, int na, int nb, int nc) {
  // na.. are 128-byte line counts; chunks of CHUNK bytes
  const int t = blockIdx.x * blockDim.x + threadIdx.x, T = gridDim.x * blockDim.x;
  const char* p[3] = {a, b, c}; const int n[3] = {na, nb, nc};
  for (int m = 0; m < 3; ++m) {
    long long bytes = (long long)n[m] * 128;
    for (long long o = (long long)t * CHUNK; o < bytes; o += (long long)T * CHUNK) {
      int size = (int)(bytes - o < CHUNK ? bytes - o : CHUNK);
      asm volatile("cp.async.bulk.prefetch.L2.global [%0], %1;" :: "l"(p[m] + o), "r"(size) : "memory");
    }
  }
}
'''
import cuda.bindings.nvrtc as nvrtc, cuda.bindings.driver as drv
prog = sc._check(nvrtc.nvrtcCreateProgram(SRC.encode(), b'pf.cu', 0, [], []))
opts = [f'--gpu-architecture={K.arch}'.encode(), f'-DCHUNK={a.bulk or 4096}'.encode()]
assert int(nvrtc.nvrtcCompileProgram(prog, len(opts), opts)[0]) == 0
cub = b' ' * sc._check(nvrtc.nvrtcGetCUBINSize(prog)); sc._check(nvrtc.nvrtcGetCUBIN(prog, cub))
torch.cuda.init(); mod = sc._check(drv.cuModuleLoadData(cub)); fn = sc._check(drv.cuModuleGetFunction(mod, b'l2_bulk' if a.bulk else b'l2_lines'))
side = torch.cuda.Stream()
def prefetch(ws):
    ws = list(ws) + [ws[0]] * (3 - len(ws)); n = [w.numel() * 2 // 128 if i < len(ws) else 0 for i, w in enumerate(ws)]
    cur = torch.cuda.current_stream(); side.wait_stream(cur)
    with torch.cuda.stream(side):
        K._launch(fn, grid=a.ctas, block=(a.threads, 1), pointers=tuple(ws), integers=tuple(n))
    return side
joins = []
orig_attn = K.attention_packed
layer_of = {}
for i, layer in enumerate(model.model.layers): layer_of[id(layer.self_attn)] = i
state_layer = {'i': 0}
orig_input = engine._decode_attention_input
layers = list(model.model.layers)
def patched_input(hidden, layer, *args, **kw):
    q = orig_input(hidden, layer, *args, **kw)
    state_layer['layer'] = layer
    return q
def patched_attn(*args, **kw):
    layer = state_layer.get('layer')
    if a.mode != 'off' and layer is not None and torch.cuda.is_current_stream_capturing():
        ws = (layer.self_attn.o_proj.weight, layer.mlp.gate_proj.weight, layer.mlp.up_proj.weight)
        if a.mode == 'gate': ws = (layer.mlp.gate_proj.weight, layer.mlp.up_proj.weight)
        if a.mode == 'o': ws = (layer.self_attn.o_proj.weight,)
        s = prefetch(ws)
        out = orig_attn(*args, **kw)
        torch.cuda.current_stream().wait_stream(s)
        state_layer['layer'] = None
        return out
    return orig_attn(*args, **kw)
engine._decode_attention_input = patched_input
K.attention_packed = patched_attn
if a.chat:
    rows = [r['tokenIds'] for r in json.loads(Path('docs/evidence/2026-10-26-vllm-impact/workload-chat-01.json').read_text())['models']['qwen']['rows'][:32]]
else:
    short = [tok(t)['input_ids'] for t in probe.PROMPTS]; rows = [short[i % 8] for i in range(32)]
run = bench.decoder_run(engine, pad=tok.pad_token_id or 0, tokens=a.tokens)
out = run(rows); run(rows)
h = hashlib.sha256(json.dumps(out).encode()).hexdigest()[:12]
ts = []
for _ in range(7):
    torch.cuda.synchronize(); t = time.perf_counter(); run(rows); torch.cuda.synchronize(); ts.append(time.perf_counter() - t)
n = sum(map(len, out))
print(f'entry {K._attention_entry} mode {a.mode} ctas {a.ctas} tokens/s {n / statistics.median(ts):.1f} median ms {statistics.median(ts)*1e3:.2f} hash {h}')
if a.trace:
    from torch.profiler import profile, ProfilerActivity
    with profile(activities=[ProfilerActivity.CUDA]) as prof:
        run(rows); torch.cuda.synchronize()
    ev = sorted((e.time_range.start, e.time_range.end, e.name) for e in prof.events() if e.device_type == torch.autograd.DeviceType.CUDA)
    st = [i for i, e in enumerate(ev) if e[2] == 'decode_layout']
    step = ev[st[-2]:st[-1]]
    agg = {}
    for b, e, nm in step: agg.setdefault(nm[:30], [0, 0.0]); agg[nm[:30]][0] += 1; agg[nm[:30]][1] += e - b
    print('step span us', round(step[-1][1] - step[0][0]), {k: (c, round(v)) for k, (c, v) in sorted(agg.items(), key=lambda kv: -kv[1][1])[:8]})
