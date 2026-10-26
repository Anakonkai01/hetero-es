"""Decode projection operator times (rows=32), cold (L2 flushed) and warm, per split-K; plus regs/occupancy."""
import argparse, os, sys, statistics
p = argparse.ArgumentParser(); p.add_argument('--gpu', action='store_true'); p.add_argument('--src', default='runtime/src')
p.add_argument('--rows', type=int, default=32); p.add_argument('--splits', default='1,2,4,8'); p.add_argument('--columns', type=int, default=32)
a = p.parse_args(); assert a.gpu and os.environ.get('HETEROES_GPU_ACCEPTANCE') == '1'
sys.path.insert(0, a.src)
import torch
from heteroes.eval import integer_cuda as ic
k = ic.IntegerCudaKernels(torch.device('cuda'), magnitude_bits=22)
drv = k._driver
gen = torch.Generator(device='cuda').manual_seed(1)
flush = torch.empty(256 * 2**20 // 4, device='cuda')
print('SMs', k.multiprocessors)
for width, outputs in ((896, 1152), (896, 896), (896, 9728), (4864, 896), (896, 151936)):
    w = (torch.randn(outputs, width, device='cuda', generator=gen) * 0.02).half()
    x = torch.randn(a.rows, width, device='cuda', generator=gen)
    k._begin_request([w])
    plan = k._decode_plan(width, min(a.rows, 128), outputs, 8)
    res = []
    for split in map(int, a.splits.split(',')):
        if split > 1 and split * a.rows * outputs * 8 > k.max_partial_bytes: continue
        flag = k.new_error_flag(); prepared = k.quantize_input(x, _packed=True)
        call = lambda: k._linear(x, w, None, row_tile=32, split_k=split, implementation='mma', prepared=prepared, stream_columns=a.columns, error_flag=flag)
        ref = call(); torch.cuda.synchronize()
        def graphed(fn, n):
            s = torch.cuda.Stream()
            with torch.cuda.stream(s):
                fn(); g = torch.cuda.CUDAGraph()
                with torch.cuda.graph(g, stream=s):
                    for _ in range(n): fn()
            torch.cuda.synchronize(); g.replay(); torch.cuda.synchronize()
            ts = []
            for _ in range(7):
                e0, e1 = torch.cuda.Event(enable_timing=True), torch.cuda.Event(enable_timing=True)
                e0.record(); g.replay(); e1.record(); torch.cuda.synchronize(); ts.append(e0.elapsed_time(e1) * 1e3 / n)
            return statistics.median(ts)
        n = 3 if outputs > 100000 else 20
        warm_t = graphed(call, n)
        both = graphed(lambda: (flush.add_(1.0), call()), 5); only = graphed(lambda: flush.add_(1.0), 5)
        cold, warm = [both - only], [warm_t]
        res.append(f's{split}: cold {statistics.median(cold):6.1f} warm {statistics.median(warm):6.1f}')
    fn = k._integer_functions(width, False, 32, 4, plan.split_k, packed_input=True, columns=a.columns)['integer_stream']
    regs = ic.sc._check(drv.cuFuncGetAttribute(drv.CUfunction_attribute.CU_FUNC_ATTRIBUTE_NUM_REGS, fn))
    smem = ic.sc._check(drv.cuFuncGetAttribute(drv.CUfunction_attribute.CU_FUNC_ATTRIBUTE_SHARED_SIZE_BYTES, fn))
    occ = ic.sc._check(drv.cuOccupancyMaxActiveBlocksPerMultiprocessor(fn, 128, 0))
    mb = w.numel() * 2 / 1e6
    tops = 2*9*a.rows*width*outputs/1e12
    print(f'[{tops:.2f} TOP] {width}x{outputs} ({mb:.1f} MB, DRAM floor {mb/845e3*1e6:.1f} us) plan split {plan.split_k} regs {regs} smem {smem} ctas/SM {occ} | ' + ' | '.join(res))
    k._end_request()
