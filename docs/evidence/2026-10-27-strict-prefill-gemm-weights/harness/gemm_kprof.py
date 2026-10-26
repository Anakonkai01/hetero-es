import os, sys, torch
from torch.profiler import profile, ProfilerActivity
sys.path.insert(0, os.environ.get('SRC', 'runtime/src'))
from heteroes.eval import integer_cuda as ic
k = ic.IntegerCudaKernels(torch.device('cuda'), magnitude_bits=22)
g = torch.Generator(device='cuda').manual_seed(1)
for width, outputs, split in ((896, 9728, 1), (896, 9728, 2), (4864, 896, 4), (4864, 896, 8), (896, 1152, 4), (896, 896, 4)):
    w = (torch.randn(outputs, width, device='cuda', generator=g) * 0.02).half(); x = torch.randn(32, width, device='cuda', generator=g)
    k._begin_request([w]); flag = k.new_error_flag(); prep = k.quantize_input(x, _packed=True)
    call = lambda: k._linear(x, w, None, row_tile=32, split_k=split, implementation='mma', prepared=prep, stream_columns=32, error_flag=flag)
    for _ in range(3): call()
    torch.cuda.synchronize()
    with profile(activities=[ProfilerActivity.CUDA]) as prof:
        for _ in range(10): call()
        torch.cuda.synchronize()
    agg = {}
    for e in prof.events():
        if e.device_type == torch.autograd.DeviceType.CUDA: agg.setdefault(e.name[:20], []).append(e.time_range.end - e.time_range.start)
    print(f'{width}x{outputs} s{split}:', {n: round(sorted(v)[len(v)//2], 1) for n, v in agg.items()})
    k._end_request()
