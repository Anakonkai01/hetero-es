"""Compile the strict ops source for each architecture and list functions containing audited-forbidden SASS."""
import re, subprocess, sys, tempfile
from pathlib import Path
import torch; torch.zeros(1, device='cuda')
from heteroes.eval import strict_cuda as sc
k = sc.StrictCudaKernels('cuda')
header = "".join(f"#define {a} 0x{b:08x}u\n" for a, b in sc.reference_constants().items())
src = header + sc._OPS_SOURCE
nv = k._nvrtc
for arch in sys.argv[1:]:
    prog = sc._check(nv.nvrtcCreateProgram(src.encode(), b"ops.cu", 0, [], []))
    opts = [f"--gpu-architecture={arch}".encode(), *(o.encode() for o in sc.NVRTC_OPTIONS)]
    assert int(nv.nvrtcCompileProgram(prog, len(opts), opts)[0]) == 0
    cubin = b" " * sc._check(nv.nvrtcGetCUBINSize(prog)); sc._check(nv.nvrtcGetCUBIN(prog, cubin))
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / 'k.cubin'; path.write_bytes(cubin)
        text = subprocess.run([k._nvdisasm, str(path)], capture_output=True, text=True, check=True).stdout
    audit = sc.audit_sass(text, sc.OPS_SASS_EXACT)
    funcs = re.split(r'\n\s*\.text\.', text)
    bad = {}
    for f in funcs[1:]:
        name = f.split(':')[0].split()[0]
        hits = [v for v in audit['violations'] if v in f]
        if hits: bad[name] = hits[:3]
    print(arch, 'violations', len(audit['violations']), bad)
