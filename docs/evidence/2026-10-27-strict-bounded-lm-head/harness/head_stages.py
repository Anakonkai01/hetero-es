"""Capture real strict final-norm activations, count surviving tiles, and time full/interval greedy paths."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import statistics
import time

p = argparse.ArgumentParser()
p.add_argument('--gpu', action='store_true')
p.add_argument('--out', type=Path, required=True)
a = p.parse_args()
assert a.gpu and os.environ.get('HETEROES_GPU_ACCEPTANCE') == '1' and not a.out.exists()
import torch
from heteroes.eval.integer_decoder import IntegerDecoderGraph
from heteroes.eval.strict_decode_cuda import DecodeKernels
from heteroes.v3.model import load, file_manifest
path = Path('/home/pc5070ti/projects/heteroes/.scratch/strict-integer-20261025/models/qwen')
model, tok = load(path, file_manifest(path), 'cuda')
engine = IntegerDecoderGraph(model, magnitude_bits=22, max_context=512, max_graph_bytes=6 * 1024**3)
head, kernels = engine._bounded_head, engine.kernels
saved = []
original = head.select

def capture(prepared, *args):
    if not saved and not torch.cuda.is_current_stream_capturing():
        saved.extend(t.clone() for t in prepared)
    return original(prepared, *args)
head.select = capture
ids = tok(['What is 3 + 5?'] * 32, return_tensors='pt', padding=True).to('cuda')
engine.generate(**ids, max_new_tokens=2, eos_token_id=[], repetition_penalty=1.0)
head.select = original
engine._generation_begin()
engine._generation_decode_ready(32, 1.0)
w = model.lm_head.weight
prepared = tuple(saved)
hi, lo = head.bounds(prepared, w)
counts = (hi >= lo.max(1, keepdim=True).values).sum(1).cpu().tolist()
print('surviving tiles', counts, flush=True)
decode = DecodeKernels(kernels)
owners = torch.arange(32, dtype=torch.int64, device='cuda')
seen = torch.zeros((32, w.shape[0]), dtype=torch.uint8, device='cuda')
tokens = torch.zeros(32, dtype=torch.int64, device='cuda')
result = torch.zeros(33, dtype=torch.int64, device='cuda')
flag = kernels.new_error_flag()
def bounded():
    head.select(prepared, w, decode, seen, owners, tokens, result, flag)
def full():
    logits = kernels.linear_decode(None, w, prepared=prepared, error_flag=flag)
    decode.greedy(logits, seen, owners, tokens, result, flag, 1.0, 1.0)

def timing(call):
    call(); torch.cuda.synchronize()
    graph = torch.cuda.CUDAGraph()
    with torch.cuda.graph(graph):
        for _ in range(8): call()
    times = []
    for _ in range(11):
        e0, e1 = torch.cuda.Event(enable_timing=True), torch.cuda.Event(enable_timing=True)
        e0.record(); graph.replay(); e1.record(); e1.synchronize()
        times.append(e0.elapsed_time(e1) * 1000 / 8)
    return times
report = {'counts': counts, 'fingerprint': engine.fingerprint, 'measurements': {}}
original_functions = head._functions

def two_stages(width, row_tile=32):
    from heteroes.eval.integer_lm_head import source
    name = f'integer-bound-stage2-{width}-m{row_tile}'
    if name not in kernels._functions:
        text = source(width, row_tile)
        start, end = text.index('extern "C" __global__ void __launch_bounds__(128) bound_scores'), text.index('// Recompute a surviving tile')
        body = text[start:end]
        for old, new in [('ws[3][32*64],as[3][3*MT*64]', 'ws[2][32*64],as[2][3*MT*64]'),
                         ('s<2;', 's<1;'), ('wait_group 1;', 'wait_group 0;'), ('it+2;', 'it+1;'), ('%3', '%2')]:
            assert old in body, old
            body = body.replace(old, new)
        text = text[:start] + body + text[end:]
        kernels._functions[name] = kernels._compile(name, text, ['bound_weights', 'bound_rows', 'bound_scores', 'bound_select'], integer_mma=True)
    return kernels._functions[name]

def stage2():
    head._functions = two_stages
    bounded()

for name, call in (('full', full), ('bounded', bounded), ('stage2', stage2)):
    samples = timing(call)
    report['measurements'][name] = {'microseconds': samples, 'median': statistics.median(samples)}
    print(name, round(statistics.median(samples), 1), flush=True)
    assert not int(flag.item())
    if name == 'full': expected = tokens.clone()
    else: assert torch.equal(tokens, expected)
    if name == 'stage2':
        actual = head.bounds(prepared, w)
        assert torch.equal(actual[0].view(torch.int32), hi.view(torch.int32))
        assert torch.equal(actual[1].view(torch.int32), lo.view(torch.int32))
report['builds'] = kernels._builds
report['resources'] = {}
for name, functions in kernels._functions.items():
    if isinstance(functions, dict) and 'bound_scores' in functions:
        fn = functions['bound_scores']
        drv = kernels._driver
        attr = drv.CUfunction_attribute
        from heteroes.eval.strict_cuda import _check
        report['resources'][name] = {
            'registers': _check(drv.cuFuncGetAttribute(attr.CU_FUNC_ATTRIBUTE_NUM_REGS, fn)),
            'sharedBytes': _check(drv.cuFuncGetAttribute(attr.CU_FUNC_ATTRIBUTE_SHARED_SIZE_BYTES, fn)),
            'residentCtas': _check(drv.cuOccupancyMaxActiveBlocksPerMultiprocessor(fn, 128, 0)),
        }
print('resources', report['resources'], flush=True)
engine._generation_end()
with a.out.open('x') as f: json.dump(report, f, indent=2)
