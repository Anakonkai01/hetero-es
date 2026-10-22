"""Qwen 0.5B: perturb + update of engine v2 by the CPU path and the GPU path; equal weights hashes and timings."""
import argparse, hashlib, json, os, platform, sys, time
import torch
from heteroes.model.loading import load_pinned_model
from heteroes.model.schema import resolve_tensors
from heteroes.es.perturb import perturb_model_
from heteroes.es.update import apply_coefficients_
from heteroes.es.snapshot import take_snapshot, restore_from_snapshot_
from heteroes.noise import engine_v2_cuda
from heteroes.noise.contracts import ENGINE_V2

p = argparse.ArgumentParser()
p.add_argument('--gpu', action='store_true'); p.add_argument('--model', required=True); p.add_argument('--out', required=True)
p.add_argument('--seeds', type=int, default=8)
a = p.parse_args()
if not a.gpu or os.environ.get('HETEROES_GPU_ACCEPTANCE') != '1':
    p.error('GPU authorization required')
loaded = load_pinned_model(a.model, 'cuda')
model, schema = loaded.model, loaded.schema
snap = take_snapshot(model, schema)
def digest():
    h = hashlib.sha256()
    for t in resolve_tensors(model, schema):
        h.update(t.detach().contiguous().view(torch.int16).cpu().numpy().tobytes())
    return h.hexdigest()
seeds = list(range(1000, 1000 + a.seeds))
coef = [((-1) ** i) * (1.0 / (i + 1)) for i in range(a.seeds)]
coef = [float(torch.tensor(c, dtype=torch.float32)) for c in coef]
result = {'host': platform.node(), 'gpu': torch.cuda.get_device_name(), 'torch': torch.__version__, 'seeds': a.seeds}
for mode in ('cpu', 'cuda', 'cpu', 'cuda'):
    os.environ[engine_v2_cuda.ENV_DEVICE] = mode
    restore_from_snapshot_(model, schema, snap)
    torch.cuda.synchronize(); t0 = time.perf_counter()
    perturb_model_(model, schema, 4242, 0.001, engine=ENGINE_V2)
    torch.cuda.synchronize(); t1 = time.perf_counter()
    perturbed = digest()
    restore_from_snapshot_(model, schema, snap)
    torch.cuda.synchronize(); t2 = time.perf_counter()
    apply_coefficients_(model, schema, seeds, coef, 0.001, engine=ENGINE_V2)
    torch.cuda.synchronize(); t3 = time.perf_counter()
    result.setdefault(mode, []).append({'perturbSeconds': t1 - t0, 'updateSeconds': t3 - t2,
                                        'perturbedSha256': perturbed, 'updatedSha256': digest()})
    print(mode, result[mode][-1], flush=True)
result['equal'] = all(r['perturbedSha256'] == result['cpu'][0]['perturbedSha256'] and r['updatedSha256'] == result['cpu'][0]['updatedSha256'] for r in result['cpu'] + result['cuda'])
json.dump(result, open(a.out, 'w'), indent=2)
print('EQUAL', result['equal'])
