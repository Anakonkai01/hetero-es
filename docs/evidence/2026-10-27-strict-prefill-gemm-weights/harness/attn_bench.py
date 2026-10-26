"""Decode GQA attention operator time (graph of 50 launches) for B queries, max_keys 512.
--skew S: row b has P[b%8]+S keys (the short32 prompts after S generated tokens). Checks equality vs strict_attention."""
import argparse, os, sys
p = argparse.ArgumentParser(); p.add_argument('--gpu', action='store_true'); p.add_argument('--src', default='runtime/src')
p.add_argument('--keys', default='16,64,128,270,512'); p.add_argument('--batch', type=int, default=32)
p.add_argument('--skew', default=''); p.add_argument('--entries', default='strict_attention_prefill')
a = p.parse_args(); assert a.gpu and os.environ.get('HETEROES_GPU_ACCEPTANCE') == '1'
sys.path.insert(0, a.src)
import torch
from heteroes.eval import strict_cuda as sc
dev = torch.device('cuda'); k = sc.StrictCudaKernels(dev)
B, H, KV, D, MAXK = a.batch, 14, 2, 64, 512
g = torch.Generator(device='cpu').manual_seed(1)
key = (torch.randn(KV, B * MAXK, D, generator=g) * 2).to(dev)
value = torch.randn(KV, B * MAXK, D, generator=g).to(dev)
q = (torch.randn(H, B, D, generator=g) * 2).to(dev)
P = [11, 27, 20, 53, 14, 82, 10, 5]
cases = [('uniform', [K] * B) for K in map(int, a.keys.split(','))] if not a.skew else \
        [(f'skew+{S}', [min(MAXK, P[b % 8] + S) for b in range(B)]) for S in map(int, a.skew.split(','))]
def timed(fn, n=50):
    s = torch.cuda.Stream()
    with torch.cuda.stream(s):
        for _ in range(3): fn()
        graph = torch.cuda.CUDAGraph()
        with torch.cuda.graph(graph, stream=s):
            for _ in range(n): fn()
    torch.cuda.synchronize(); graph.replay(); torch.cuda.synchronize(); ts = []
    for _ in range(5):
        e0, e1 = torch.cuda.Event(enable_timing=True), torch.cuda.Event(enable_timing=True)
        e0.record(); graph.replay(); e1.record(); torch.cuda.synchronize(); ts.append(e0.elapsed_time(e1) * 1e3 / n)
    return sorted(ts)[2]
for name, lens in cases:
    ranges = torch.tensor([x for b in range(B) for x in (b * MAXK, lens[b], lens[b] - 1)], dtype=torch.int32, device=dev)
    layout = sc._PackedAttentionLayout(ranges, B, B * MAXK, MAXK)
    flag = k.new_error_flag()
    k._attention_entry = 'strict_attention'
    ref = k.attention_packed(q, key, value, layout, H // KV, 0.125, error_flag=flag)
    row = []
    for entry in a.entries.split(','):
        k._attention_entry = entry
        out = k.attention_packed(q, key, value, layout, H // KV, 0.125, error_flag=flag)
        same = torch.equal(out.view(torch.int32), ref.view(torch.int32))
        t = timed(lambda: k.attention_packed(q, key, value, layout, H // KV, 0.125, error_flag=flag))
        row.append(f'{entry} {t:6.2f} us eq={same}')
    print(f'{name:10s} max {max(lens):4d} sum {sum(lens):5d} | ' + ' | '.join(row) + f' | flag={int(flag.item())}')
