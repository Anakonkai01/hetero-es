"""Compare documented signed FTZ primitives with explicit integer-flush operations; scratch only."""
import argparse
import hashlib
import json
import os
from pathlib import Path

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--gpu', action='store_true')
p.add_argument('--out', type=Path, required=True)
a = p.parse_args()
if not a.gpu or os.environ.get('HETEROES_GPU_ACCEPTANCE') != '1' or a.out.exists():
    p.error('Need GPU acceptance and fresh receipt')
import torch
from heteroes.eval import strict_cuda as sc

original_ptx, original_sass = sc.audit_ptx, sc.audit_sass
# Research-only audits explicitly normalize the *two selected* primitive opcodes; no FMA/other FTZ is admitted.
def audit_ptx(text, exact=()):
    text = text.replace('add.rn.ftz.f32', 'add.rn.f32').replace('mul.rn.ftz.f32', 'mul.rn.f32')
    return original_ptx(text, exact)
def audit_sass(text, exact=()):
    text = text.replace('FADD.FTZ ', 'FADD ').replace('FMUL.FTZ ', 'FMUL ')
    return original_sass(text, exact)
sc.audit_ptx, sc.audit_sass = audit_ptx, audit_sass
source = r'''
extern "C" __global__ void probe(const float* a, const float* b, float* add, float* mul, int n) {
 int i=blockIdx.x*blockDim.x+threadIdx.x;
 if(i<n) {
  float x=a[i],y=b[i],s,p;
  asm volatile("add.rn.ftz.f32 %0, %1, %2;" : "=f"(s) : "f"(x), "f"(y));
  asm volatile("mul.rn.ftz.f32 %0, %1, %2;" : "=f"(p) : "f"(x), "f"(y));
  add[i]=s;mul[i]=p;
 }
}
'''
report = {'status': 'running', 'hardwareQualified': False, 'gpu': torch.cuda.get_device_name(),
          'sourceSha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), 'cases': [],
          'limits': 'Finite primitive study, not adoption/qualification. Scratch audit normalization only admits '
                    'the two explicitly selected native signed-FTZ operations.'}
try:
    torch.set_num_threads(4)
    kernels = sc.StrictCudaKernels('cuda')
    gen = torch.Generator().manual_seed(741)
    edge = torch.tensor([0, 1, 0x007fffff, 0x00800000, 0x00800001, 0x00800002, 0x01000000, 0x3effffff,
                         0x3f000000, 0x3f000001, 0x3f7ffffe, 0x3f7fffff, 0x3f800000, 0x3f800001,
                         0x3f800002, 0x3fffffff, 0x40000000, 0x7f7ffffe, 0x7f7fffff], dtype=torch.int64)
    edge = torch.cat((edge, edge | 0x80000000)).to(torch.int32)
    xs, ys = [edge.repeat_interleave(edge.numel())], [edge.repeat(edge.numel())]
    # Sweep minimum-normal neighborhoods and multipliers on both sides of one, including halfway rounding.
    near = torch.arange(0x00800000-4096, 0x00800000+4097, dtype=torch.int32)
    factors = torch.arange(0x3f800000-64, 0x3f800000+65, dtype=torch.int32)
    xs += [near.repeat_interleave(factors.numel())]; ys += [factors.repeat(near.numel())]
    for _ in range(4):
        u = torch.randint(-(2**31), 2**31, (524288,), generator=gen, dtype=torch.int32)
        v = torch.randint(-(2**31), 2**31, (524288,), generator=gen, dtype=torch.int32)
        valid = ((u & 0x7f800000) != 0x7f800000) & ((v & 0x7f800000) != 0x7f800000)
        xs.append(u[valid]); ys.append(v[valid])
    x, y = torch.cat(xs).view(torch.float32), torch.cat(ys).view(torch.float32)
    def flush(v):
        bits = v.contiguous().view(torch.int32)
        return torch.where((bits & 0x7f800000) == 0, bits & -2147483648, bits).view(torch.float32)
    expected = (flush(flush(x) + flush(y)), flush(flush(x) * flush(y)))
    gx, gy = x.cuda(), y.cuda()
    actual = (torch.empty_like(gx), torch.empty_like(gx))
    function = kernels._compile('probe-native-ftz', source, ['probe'])['probe']
    kernels._launch(function, grid=-(-x.numel()//256), block=(256,1), pointers=(gx,gy,*actual), integers=(x.numel(),))
    for name, exp, act in zip(('add','mul'), expected, actual):
        act = act.cpu()
        match = (exp.view(torch.int32) == act.view(torch.int32)) | (torch.isnan(exp) & torch.isnan(act))
        wrong = (~match).nonzero().flatten()
        indices = wrong[:20]
        report['cases'].append({'operation': name, 'count': x.numel(), 'differences': wrong.numel(),
                                'counterexamples': [{'a': int(x.view(torch.int32)[i]), 'b': int(y.view(torch.int32)[i]),
                                                     'cpu': int(exp.view(torch.int32)[i]), 'cuda': int(act.view(torch.int32)[i])}
                                                    for i in indices]})
    report['identity'] = kernels.identity()
    report['status'] = 'ok' if all(c['differences']==0 for c in report['cases']) else 'counterexample'
except Exception as exc:
    report.update(status='error', errorType=type(exc).__name__, error=str(exc))
with a.out.open('x') as f:
    json.dump(report, f, indent=2); f.write('\n')
print(json.dumps({k: report[k] for k in ('status','cases')}))
raise SystemExit(report['status'] != 'ok')
