"""Cost of a kernel boundary inside a CUDA graph: chains of tiny kernels with various grid sizes."""
import os, statistics, torch
import cuda.bindings.nvrtc as nvrtc, cuda.bindings.driver as drv
from heteroes.eval import strict_cuda as sc
os.environ['HETEROES_GPU_ACCEPTANCE'] = '1'
k = sc.StrictCudaKernels(torch.device('cuda'))
SRC = r'''extern "C" __global__ void tiny(float* p, int n) { int i = blockIdx.x * blockDim.x + threadIdx.x; if (i < n) p[i] = p[i] * 1.0001f + 1.0f; }'''
prog = sc._check(nvrtc.nvrtcCreateProgram(SRC.encode(), b't.cu', 0, [], []))
opts = [f'--gpu-architecture={k.arch}'.encode()]
assert int(nvrtc.nvrtcCompileProgram(prog, 1, opts)[0]) == 0
cub = b' ' * sc._check(nvrtc.nvrtcGetCUBINSize(prog)); sc._check(nvrtc.nvrtcGetCUBIN(prog, cub))
torch.zeros(1, device='cuda'); mod = sc._check(drv.cuModuleLoadData(cub)); fn = sc._check(drv.cuModuleGetFunction(mod, b'tiny'))
buf = torch.zeros(1 << 22, device='cuda')
for blocks, threads in ((1, 32), (32, 256), (70, 256), (280, 256), (1120, 256)):
    s = torch.cuda.Stream()
    with torch.cuda.stream(s):
        g = torch.cuda.CUDAGraph()
        with torch.cuda.graph(g, stream=s):
            for _ in range(200): k._launch(fn, grid=blocks, block=(threads, 1), pointers=(buf,), integers=(blocks * threads,))
    torch.cuda.synchronize(); g.replay(); torch.cuda.synchronize(); ts = []
    for _ in range(7):
        e0, e1 = torch.cuda.Event(enable_timing=True), torch.cuda.Event(enable_timing=True)
        e0.record(); g.replay(); e1.record(); torch.cuda.synchronize(); ts.append(e0.elapsed_time(e1) * 1e3 / 200)
    print(f'grid {blocks:5d} x {threads}: {statistics.median(ts):.2f} us per kernel')
