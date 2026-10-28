"""Standalone probe: engine v2 on this machine's GPU equals the CPU engine (chunks, self-test, toy perturb+update)."""
import hashlib, json, os, platform, sys, time
sys.path.insert(0, sys.argv[1])
import numpy as np, torch, torch.nn as nn
from heteroes.noise import engine_v2_cuda
from heteroes.noise.contracts import ENGINE_V2, ChunkNoiseAddress
from heteroes.noise.engine_v2 import generate_chunk_noise
from heteroes.es.perturb import perturb_model_
from heteroes.es.update import apply_coefficients_
from heteroes.model.schema import build_parameter_schema
assert os.environ.get('HETEROES_GPU_ACCEPTANCE') == '1' and '--gpu' in sys.argv
dev = torch.device('cuda')
out = {'host': platform.node(), 'platform': platform.platform(), 'gpu': torch.cuda.get_device_name(), 'torch': torch.__version__}
t = time.perf_counter(); out['selftest'] = engine_v2_cuda.selftest(dev); out['firstUseSeconds'] = time.perf_counter() - t
rng = np.random.default_rng(99)
addrs = [ChunkNoiseAddress(int(rng.integers(0, 2**63)), 'probe', int(rng.integers(0, 300)), i, 2**18) for i in range(64)]
lens = [2**18] * 63 + [2**18 - 3]
made = engine_v2_cuda.generate_chunks(addrs, lens, dev).cpu().numpy().view(np.uint16)
ref = np.concatenate([generate_chunk_noise(a, n) for a, n in zip(addrs, lens)]).view(np.uint16)
out['chunksEqual'] = bool(np.array_equal(made, ref)); out['chunksSha256'] = hashlib.sha256(made.tobytes()).hexdigest()
torch.cuda.synchronize(); t = time.perf_counter()
for _ in range(10): engine_v2_cuda.generate_chunks(addrs[:16], lens[:16], dev)
torch.cuda.synchronize(); out['msPerChunk'] = (time.perf_counter() - t) / 160 * 1000
class Toy(nn.Module):
    def __init__(self):
        super().__init__(); self.embed = nn.Embedding(300, 700); self.fc = nn.Linear(700, 3); self.half()
torch.manual_seed(0); base = Toy().cuda(); schema = build_parameter_schema(base); hashes = {}
for mode in ('cuda', 'cpu'):
    os.environ[engine_v2_cuda.ENV_DEVICE] = mode
    m = Toy().cuda(); m.load_state_dict(base.state_dict())
    perturb_model_(m, schema, 77, 0.01, 2**16, engine=ENGINE_V2)
    apply_coefficients_(m, schema, [5, 6, 9], [1.0, -0.5, 0.25], 0.01, 2**16, engine=ENGINE_V2)
    h = hashlib.sha256()
    for p in m.parameters(): h.update(p.detach().cpu().contiguous().view(torch.int16).numpy().tobytes())
    hashes[mode] = h.hexdigest()
out['toyHashes'] = hashes; out['toyEqual'] = hashes['cuda'] == hashes['cpu']
print(json.dumps(out))
