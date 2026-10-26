"""Kernel-only durations (CUPTI) for decode/prefill attention shapes; host launch cost excluded."""
import os, sys, torch, statistics
from torch.profiler import profile, ProfilerActivity
from heteroes.eval import strict_cuda as sc
k = sc.StrictCudaKernels('cuda')
heads, kvh, dim, context = int(os.environ.get('HEADS', 14)), int(os.environ.get('KVH', 2)), int(os.environ.get('DIM', 64)), 512
rep = heads // kvh
g = torch.Generator().manual_seed(0)
ENTRIES = ('strict_attention', 'strict_attention_split', 'strict_attention_gqa')
def kernel_us(layout, q, K, V):
    res = {}
    for entry in ENTRIES:
        k._attention_entry = entry; flag = k.new_error_flag()
        out = k.attention_packed(q, K, V, layout, rep, 0.125, error_flag=flag); torch.cuda.synchronize()
        with profile(activities=[ProfilerActivity.CUDA]) as prof:
            for _ in range(20): k.attention_packed(q, K, V, layout, rep, 0.125, error_flag=flag)
            torch.cuda.synchronize()
        d = [e.time_range.end - e.time_range.start for e in prof.events() if e.name.startswith('strict_attention')]
        res[entry] = (out, statistics.median(d), int(flag.item()))
    base = res['strict_attention']
    assert all(torch.equal(r[0].view(torch.int32), base[0].view(torch.int32)) and r[2] == base[2] for r in res.values())
    return res
rows = 32
K = torch.randn(kvh, rows * context, dim, generator=g).cuda(); V = torch.randn_like(K)
q = torch.randn(heads, rows, dim, generator=g).cuda()
for keys in (64, 143, 270, 512):
    ranges = torch.tensor(sum(([i * context, keys, keys - 1] for i in range(rows)), []), dtype=torch.int32).cuda()
    res = kernel_us(sc._PackedAttentionLayout(ranges, rows, rows * context, context), q, K, V)
    print(f'heads {heads}/{kvh} dim {dim} decode keys {keys:4d}: ' + '  '.join(f'{e[17:] or "original"} {r[1]:7.1f}us x{res[ENTRIES[0]][1]/r[1]:.2f}' for e, r in res.items()), flush=True)
L = 142
ranges = torch.tensor(sum(([s * context, L, t] for s in range(rows) for t in range(L)), []), dtype=torch.int32).cuda()
qp = torch.randn(heads, rows * L, dim, generator=g).cuda()
res = kernel_us(sc._PackedAttentionLayout(ranges, rows * L, rows * context, context), qp, K, V)
print(f'heads {heads}/{kvh} dim {dim} prefill 32x142: ' + '  '.join(f'{e[17:] or "original"} {r[1]:8.1f}us x{res[ENTRIES[0]][1]/r[1]:.2f}' for e, r in res.items()))
