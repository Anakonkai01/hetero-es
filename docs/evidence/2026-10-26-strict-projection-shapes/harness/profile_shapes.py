"""CUPTI per-shape durations of the selected B22 decode projection kernels (no timing nodes, no host launch cost).

Uses the trained Qwen weights (layer 0 projections and the tied head) with the decode plan the graph selects,
reports achieved weight bytes/s and int8 MMA ops/s, and a plain device read of the same weights as a floor.
"""
import argparse, hashlib, json, os, statistics
from pathlib import Path
p = argparse.ArgumentParser(); p.add_argument('--gpu', action='store_true'); p.add_argument('--out', type=Path, required=True)
p.add_argument('--rows', type=int, nargs='+', default=[8, 32]); p.add_argument('--repeats', type=int, default=20)
p.add_argument('--model', default='/home/pc5070ti/projects/heteroes/.scratch/strict-integer-20261025/models/qwen')
a = p.parse_args()
if not a.gpu or os.environ.get('HETEROES_GPU_ACCEPTANCE') != '1' or a.out.exists(): p.error('GPU opt-in/fresh output required')
import torch
from torch.profiler import profile, ProfilerActivity
from heteroes.eval.integer_cuda import IntegerCudaKernels
from heteroes.v3.model import load, file_manifest
path = Path(a.model); files = file_manifest(path)
model, _ = load(path, files, 'cuda')
layer = model.model.layers[0]
mods = {'q': layer.self_attn.q_proj, 'k': layer.self_attn.k_proj, 'v': layer.self_attn.v_proj, 'o': layer.self_attn.o_proj,
        'gate': layer.mlp.gate_proj, 'up': layer.mlp.up_proj, 'down': layer.mlp.down_proj, 'head': model.lm_head}
kernels = IntegerCudaKernels(torch.device('cuda'), magnitude_bits=22)
kernels._begin_request([m.weight for m in mods.values()])
gen = torch.Generator(device='cuda').manual_seed(7)


def kernel_ms(fn):
    fn(); torch.cuda.synchronize()
    with profile(activities=[ProfilerActivity.CUDA]) as prof:
        for _ in range(a.repeats): fn()
        torch.cuda.synchronize()
    by = {}
    for e in prof.events():
        if e.device_type == torch.autograd.DeviceType.CUDA:
            by.setdefault(e.name, []).append((e.time_range.end - e.time_range.start) / 1e3)
    return {n: {'count': len(v), 'medianMs': statistics.median(v)} for n, v in by.items()}


report = {'gpu': torch.cuda.get_device_name(), 'sm': kernels.arch, 'multiprocessors': kernels.multiprocessors,
          'torch': torch.__version__, 'modelFiles': files, 'repeats': a.repeats,
          'sourceSha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
          'integerCudaSha256': hashlib.sha256(Path(kernels.__module__.replace('.', '/') + '.py').read_bytes()).hexdigest()
          if Path(kernels.__module__.replace('.', '/') + '.py').exists() else None, 'shapes': []}
for name, m in mods.items():
    w = m.weight; outputs, width = w.shape
    # plain read floor: one fused reduction over the same FP16 bytes
    floor = kernel_ms(lambda: w.sum(dtype=torch.float32))
    floor_ms = min(v['medianMs'] for v in floor.values())
    for rows in a.rows:
        x = torch.randn(rows, width, device='cuda', generator=gen)
        plan = kernels._decode_plan(width, rows, outputs, 8)
        flag = kernels.new_error_flag()
        res = kernel_ms(lambda: kernels.linear_decode(x, w, getattr(m, 'bias', None), error_flag=flag))
        kernels.raise_if_error(flag)
        lin = res.get('integer_linear') or res.get('integer_simt')
        total = sum(v['medianMs'] for k, v in res.items() if k.startswith('integer_'))
        gbytes = 2 * outputs * width / 1e9
        mma_tops = 2 * 9 * (-(-rows // 16) * 16) * outputs * width / 1e12
        entry = {'name': name, 'width': width, 'outputs': outputs, 'rows': rows, 'plan': plan.__dict__, 'kernels': res,
                 'linearMs': lin['medianMs'], 'allIntegerMs': total, 'plainReadMs': floor_ms,
                 'linearWeightGBps': gbytes / (lin['medianMs'] / 1e3), 'plainReadGBps': gbytes / (floor_ms / 1e3),
                 'paddedMmaTops': mma_tops / (lin['medianMs'] / 1e3)}
        report['shapes'].append(entry)
        print(f"{name:5s} {width:5d}->{outputs:6d} rows {rows:3d} split {plan.split_k} tile {plan.row_tile} "
              f"linear {lin['medianMs']*1e3:8.1f}us all {total*1e3:8.1f}us read {floor_ms*1e3:7.1f}us "
              f"{entry['linearWeightGBps']:6.0f} GB/s (read {entry['plainReadGBps']:4.0f}) {entry['paddedMmaTops']:6.1f} TOPS", flush=True)
kernels._end_request()
report['status'] = 'ok'
with a.out.open('x') as f: json.dump(report, f, indent=2); f.write('\n')
