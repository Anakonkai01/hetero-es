"""Feasibility: how many vocab rows survive a rigorous bound from a b-bit truncated lm_head (B22 row scales)?"""
import importlib.util, torch, math
from pathlib import Path
from transformers import AutoModelForCausalLM, AutoTokenizer
path = '/home/pc5070ti/projects/heteroes/.scratch/strict-integer-20261025/models/qwen'
tok = AutoTokenizer.from_pretrained(path)
model = AutoModelForCausalLM.from_pretrained(path, torch_dtype=torch.float32).cuda().eval()
spec = importlib.util.spec_from_file_location('probe', 'runtime/scripts/probe_strict_backend.py'); probe = importlib.util.module_from_spec(spec); spec.loader.exec_module(probe)
import json
chat = [r['tokenIds'] for r in json.loads(Path('docs/evidence/2026-10-26-vllm-impact/workload-chat-01.json').read_text())['models']['qwen']['rows'][:16]]
rows = [tok(t)['input_ids'] for t in probe.PROMPTS] + chat
hs = []
with torch.no_grad():
    for r in rows:
        out = model.generate(torch.tensor([r]).cuda(), max_new_tokens=32, do_sample=False, output_hidden_states=True, return_dict_in_generate=True)
        for step in out.hidden_states[1:]:
            hs.append(model.model.norm(step[-1][0, -1]).float())
H = torch.stack(hs)  # [N, 896] final-normed hidden states (FP32 reference, close to strict)
W = model.lm_head.weight.detach().half().float()  # FP16 weights as stored
B = 21
def q_rows(x):
    m = x.abs().amax(1, keepdim=True); e = torch.floor(torch.log2(m)); return torch.round(x * 2.0 ** (B - e)), e
qa, ea = q_rows(H.double()); qw, ew = q_rows(W.double())
S = qa @ qw.T  # exact in float64 (|S| < 2^52)
L = S * 2.0 ** (-(2 * B) + ea + ew.T)
best = L.argmax(1)
l1 = qa.abs().sum(1, keepdim=True)
for bits in (7,):
    shift = B + 1 - bits  # t has `bits` signed bits
    t = torch.round(qw / 2.0 ** shift); err = 2.0 ** (shift - 1)
    approx = (qa @ t.T) * 2.0 ** shift
    bound = l1 * err
    up = (approx + bound) * 2.0 ** (-(2 * B) + ea + ew.T); lo = (approx - bound) * 2.0 ** (-(2 * B) + ea + ew.T)
    best_lo = lo.max(1, keepdim=True).values
    survivors = (up >= best_lo).sum(1).float()
    ok = (up.gather(1, best[:, None]) >= best_lo).all()
    print(f'{bits}-bit weights: survivors per row median {survivors.median():.0f} mean {survivors.mean():.1f} max {survivors.max():.0f} of {W.shape[0]}; argmax kept {bool(ok)}')
# activation also truncated to 8 bits
for wb, ab in ((7, 16), (7, 14)):
    ws = B + 1 - wb; as_ = B + 1 - ab
    t = torch.round(qw / 2.0 ** ws); u = torch.round(qa / 2.0 ** as_)
    approx = (u @ t.T) * 2.0 ** (ws + as_)
    # |qa qw - u t 2^(as+ws)| <= |qa||qw - t 2^ws| + |t 2^ws||qa - u 2^as|
    bound = qa.abs() @ torch.full_like(qw[0], 2.0 ** (ws - 1))[:, None].expand(-1, 1) * 0  # placeholder
    bound = (qa.abs().sum(1, keepdim=True) * 2.0 ** (ws - 1)) + (2.0 ** (as_ - 1)) * (t.abs() * 2.0 ** ws).sum(1)[None, :]
    up = (approx + bound) * 2.0 ** (-(2 * B) + ea + ew.T); lo = (approx - bound) * 2.0 ** (-(2 * B) + ea + ew.T)
    best_lo = lo.max(1, keepdim=True).values
    survivors = (up >= best_lo).sum(1).float()
    print(f'{wb}-bit w x {ab}-bit a: survivors median {survivors.median():.0f} mean {survivors.mean():.1f} max {survivors.max():.0f}')
print('rows', H.shape[0], 'top-2 logit gap median', (L.topk(2, 1).values[:, 0] - L.topk(2, 1).values[:, 1]).median().item())

# tile-level survivors (32 vocab per tile), 7-bit floor+offset weights, exact activations
shift = 15; t = torch.floor(qw / 2.0 ** shift); approx = (qa @ t.T) * 2.0 ** shift + 2.0 ** 14 * qa.sum(1, keepdim=True)
bound = l1 * 2.0 ** 14
up = (approx + bound) * 2.0 ** (-(2 * B) + ea + ew.T); lo = (approx - bound) * 2.0 ** (-(2 * B) + ea + ew.T)
assert (up >= L - 1e-9).all() and (lo <= L + 1e-9).all()
best_lo = lo.max(1, keepdim=True).values
V = W.shape[0]; T = (V + 31) // 32
pad = torch.full((up.shape[0], T * 32 - V), -1e30, dtype=up.dtype, device=up.device)
tu = torch.cat([up, pad], 1).view(up.shape[0], T, 32).amax(2)
st = (tu >= best_lo).sum(1).float()
print(f'floor7+offset: tiles surviving per row median {st.median():.0f} mean {st.mean():.2f} max {st.max():.0f} of {T}')
