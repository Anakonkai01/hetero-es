import os, sys, numpy as np, torch
sys.path.insert(0, '.scratch/claude-20261026-night/src4')
from heteroes.eval import integer_cuda as ic
k = ic.IntegerCudaKernels(torch.device('cuda'), magnitude_bits=22); drv = k._driver
g = torch.Generator(device='cuda').manual_seed(1)
for width, outputs, split in ((896, 9728, 1), (896, 9728, 2), (4864, 896, 8), (896, 151936, 1)):
    w = (torch.randn(outputs, width, device='cuda', generator=g) * 0.02).half(); x = torch.randn(32, width, device='cuda', generator=g)
    k._begin_request([w]); flag = k.new_error_flag(); prep = k.quantize_input(x, _packed=True)
    call = lambda: k._linear(x, w, None, row_tile=32, split_k=split, implementation='mma', prepared=prep, stream_columns=32, error_flag=flag)
    call(); torch.cuda.synchronize()
    fn = k._integer_functions(width, False, 32, 4, split, packed_input=True, columns=32)
    mod = k._modules[-1]
    ptr, size = ic.sc._check(drv.cuModuleGetGlobal(mod, b'prof_acc'))
    ic.sc._check(drv.cuMemsetD8(ptr, 0, size)); torch.cuda.synchronize()
    for _ in range(10): call()
    torch.cuda.synchronize()
    buf = np.zeros(8, dtype=np.uint64); ic.sc._check(drv.cuMemcpyDtoH(buf.ctypes.data, ptr, size))
    wait, comp, tot, n = buf[:4].astype(float)
    print(f'{width}x{outputs} s{split}: per warp wait {wait/n:8.0f} compute {comp/n:8.0f} total-in-body {tot/n:8.0f} cycles  (warps {n/10:.0f}/call)')
    k._end_request()
