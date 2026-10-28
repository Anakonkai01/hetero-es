"""Retain actual audited scalar/paired/prefetch2 B22 PTX and SASS; no model or timing."""
import argparse
import hashlib
import json
import os
from pathlib import Path

import torch

from heteroes.eval import integer_cuda as ic
from heteroes.eval import strict_cuda as sc

p = argparse.ArgumentParser()
p.add_argument('--out', type=Path, required=True)
p.add_argument('--gpu', action='store_true')
a = p.parse_args()
if a.out.exists():
    p.error('Existing evidence')
if not a.gpu or os.environ.get('HETEROES_GPU_ACCEPTANCE') != '1':
    p.error('GPU opt-in')
context = torch.empty(1, device='cuda')
a.out.mkdir(parents=True)
label = ''
for name, suffix in (('audit_integer_ptx', 'ptx'), ('audit_integer_sass', 'sass')):
    original = getattr(sc, name)

    def wrapped(text, *args, _original=original, _suffix=suffix, **kwargs):
        (a.out / (label + '.' + _suffix)).write_text(text)
        return _original(text, *args, **kwargs)

    setattr(sc, name, wrapped)
identities = {}
for mode in ('scalar', 'paired', 'prefetch2'):
    k = ic.IntegerCudaKernels('cuda', magnitude_bits=22, weight_load=mode)
    for width in (896, 2048):
        label = f'b22-{mode}-k{width}-{k.arch}'
        k._integer_functions(width, row_tile=16, warps=4, split_k=1, packed_input=True)
    identities[mode] = k.identity()
report = {'sourceSha256': hashlib.sha256(Path(ic.__file__).read_bytes()).hexdigest(), 'identities': identities}
with (a.out / 'identity.json').open('x') as f:
    json.dump(report, f, indent=2)
    f.write('\n')
