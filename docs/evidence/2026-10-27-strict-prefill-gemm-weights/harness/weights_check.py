"""Batched exponents equal the per-weight kernel, including flags; timing of both."""
import sys, torch, time
from heteroes.eval import integer_cuda as ic
torch.zeros(1, device='cuda'); k = ic.IntegerCudaKernels(torch.device('cuda'), magnitude_bits=22)
g = torch.Generator(device='cuda').manual_seed(5)
ws = [(torch.randn(r, c, device='cuda', generator=g) * s).half() for r, c, s in ((896, 896, 0.02), (128, 896, 1e-6), (4864, 896, 3.0), (896, 4864, 0.001), (37, 64, 1e3), (151936, 896, 0.05))]
ws[1][3, 5] = 0; ws[1][7] = 0; ws[4][2, 3] = float('inf'); ws[2][4, 0] = 6e-8  # subnormal
for bad in (False, True):
    sel = ws if bad else [w for i, w in enumerate(ws) if i != 4]
    ref = [torch.empty(w.shape[0], dtype=torch.int32, device='cuda') for w in sel]
    new = [torch.full((w.shape[0],), 99, dtype=torch.int32, device='cuda') for w in sel]
    f1, f2 = k.new_error_flag(), k.new_error_flag()
    for w, e in zip(sel, ref): k._refresh_weight_exponents(w, e, f1)
    k._refresh_exponents_batched(list(zip(sel, new)), f2)
    torch.cuda.synchronize()
    print('bad', bad, 'equal', all(torch.equal(a, b) for a, b in zip(ref, new)), 'flags', int(f1.item()), int(f2.item()))
