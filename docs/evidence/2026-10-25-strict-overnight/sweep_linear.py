"""Scratch-only exact-tree decomposition sweep, no live implementation changes."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import statistics
import time

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--gpu', action='store_true')
p.add_argument('--out', type=Path, required=True)
a = p.parse_args()
if not a.gpu or os.environ.get('HETEROES_GPU_ACCEPTANCE') != '1' or a.out.exists():
    p.error('Need GPU acceptance and fresh receipt')
import torch
from heteroes.eval.strict_cuda import StrictCudaKernels, LinearPlan, linear_plan, _check
from heteroes.eval import reference_ops as ops

report = {'status': 'running', 'gpu': torch.cuda.get_device_name(), 'cases': [], 'hardwareQualified': False,
          'sourceSha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
          'limits': 'Finite synthetic matrices. Captured repeated raw launches isolate CUDA cost; not decoder throughput. '
                    'All outputs compare with the prior strict kernel, sampled columns with CPU oracle.'}
try:
    for width, outputs in ((768, 4096), (1024, 32768), (2048, 11008), (4096, 4096)):
        gen = torch.Generator().manual_seed(width)
        weight = (torch.randn(outputs, width, generator=gen) * .02).half().cuda()
        x = torch.randn(32, width, generator=gen).cuda()
        base = StrictCudaKernels('cuda')
        expected = base.linear(x, weight)
        oracle = ops.linear(x[:3].cpu(), weight[:3].cpu())
        assert torch.equal(expected[:3, :3].cpu().contiguous().view(torch.int32), oracle.view(torch.int32))
        for per in (2, 4, 8, 16, 32):
            warps = -(-width // (32 * per))
            if warps > 32:
                continue
            padded_warps = 1 << (warps - 1).bit_length()
            groups = max(1, 8 // warps)
            plan = LinearPlan(width, 1 << (width - 1).bit_length(), per, warps, padded_warps, groups)
            # One compiler instance per decomposition: live cache names predate configurable decomposition.
            kernels = StrictCudaKernels('cuda')
            for tile in (4, 8, 16, 32):
                function = kernels._linear_function(plan, False, tile)
                result = torch.empty_like(expected)
                flag = kernels.new_error_flag()
                def launch():
                    kernels._launch(function, grid=(-(-outputs // groups), -(-32 // tile)),
                                    block=(32 * warps, groups), pointers=(x, weight, weight, result, flag),
                                    integers=(32, outputs))
                launch(); kernels.raise_if_error(flag)
                assert torch.equal(result.view(torch.int32), expected.view(torch.int32)), (width, per, tile)
                g = torch.cuda.CUDAGraph()
                with torch.cuda.graph(g):
                    for _ in range(20):
                        launch()
                ms = []
                for _ in range(3):
                    start, end = torch.cuda.Event(enable_timing=True), torch.cuda.Event(enable_timing=True)
                    start.record(); g.replay(); end.record(); end.synchronize()
                    ms.append(start.elapsed_time(end) / 20)
                kernels.raise_if_error(flag)
                attrs = {}
                for name in ('CU_FUNC_ATTRIBUTE_NUM_REGS', 'CU_FUNC_ATTRIBUTE_LOCAL_SIZE_BYTES', 'CU_FUNC_ATTRIBUTE_SHARED_SIZE_BYTES'):
                    attr = getattr(kernels._driver.CUfunction_attribute, name)
                    attrs[name] = _check(kernels._driver.cuFuncGetAttribute(attr, function))
                case = {'width': width, 'outputs': outputs, 'rows': 32, 'per': per, 'warps': warps, 'groups': groups,
                        'tile': tile, 'eventMs': ms, 'medianEventMs': statistics.median(ms), 'attributes': attrs,
                        'bitsEqual': True, 'build': kernels.identity()['builds']}
                report['cases'].append(case)
                print(json.dumps({k: case[k] for k in ('width', 'per', 'tile', 'medianEventMs', 'attributes')}), flush=True)
                del g
        del weight, x, expected, base
    report['status'] = 'ok'
except Exception as exc:
    report.update(status='error', errorType=type(exc).__name__, error=str(exc))
with a.out.open('x') as f:
    json.dump(report, f, indent=2); f.write('\n')
print(json.dumps({'status': report['status'], 'error': report.get('error')}))
raise SystemExit(report['status'] != 'ok')
