"""Compile the ops source of two strict_cuda.py files for several targets and compare PTX/cubin hashes."""
import hashlib, importlib.util, sys
import torch; torch.zeros(1, device='cuda')
def ops_source(path):
    spec = importlib.util.spec_from_file_location('m' + hashlib.sha256(path.encode()).hexdigest()[:8], path)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    return "".join(f"#define {a} 0x{b:08x}u\n" for a, b in m.reference_constants().items()) + m._OPS_SOURCE, m
from cuda.bindings import nvrtc
def build(src, arch, sc):
    prog = sc._check(nvrtc.nvrtcCreateProgram(src.encode(), b"ops.cu", 0, [], []))
    opts = [f"--gpu-architecture={arch}".encode(), *(o.encode() for o in sc.NVRTC_OPTIONS)]
    assert int(nvrtc.nvrtcCompileProgram(prog, len(opts), opts)[0]) == 0
    ptx = b" " * sc._check(nvrtc.nvrtcGetPTXSize(prog)); sc._check(nvrtc.nvrtcGetPTX(prog, ptx))
    cub = b" " * sc._check(nvrtc.nvrtcGetCUBINSize(prog)); sc._check(nvrtc.nvrtcGetCUBIN(prog, cub))
    return hashlib.sha256(ptx).hexdigest(), hashlib.sha256(cub).hexdigest()
(a, ma), (b, mb) = ops_source(sys.argv[1]), ops_source(sys.argv[2])
for arch in ('sm_86', 'sm_120'):
    x, y = build(a, arch, ma), build(b, arch, mb)
    print(arch, 'ptx equal', x[0] == y[0], 'cubin equal', x[1] == y[1])
