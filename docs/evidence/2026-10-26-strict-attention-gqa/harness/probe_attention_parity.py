#!/usr/bin/env python3
"""Original vs distributed strict attention in the selected B22 decoder: parent, canonical seed pair, restore.

Same-host bit equality (prefill logits, tokens) is required; cross-host comparison is done afterwards from the
receipts. Finite numerical evidence only: no quality, learning, managed lifecycle or hardware qualification.
"""
import argparse, hashlib, json, os, platform, time
from pathlib import Path

p = argparse.ArgumentParser()
p.add_argument('--model-path', type=Path, required=True)
p.add_argument('--chat-workload', type=Path)
p.add_argument('--model-name', required=True)
p.add_argument('--out', type=Path, required=True)
p.add_argument('--gpu', action='store_true')
a = p.parse_args()
if not a.gpu or os.environ.get('HETEROES_GPU_ACCEPTANCE') != '1' or a.out.exists():
    p.error('GPU opt-in and a fresh --out are required')
import torch, transformers
from heteroes.es.perturb import perturb_model_
from heteroes.es.snapshot import restore_from_snapshot_, take_snapshot
from heteroes.eval.candidate import model_weights_sha256
from heteroes.eval.integer_decoder import IntegerDecoderGraph
from heteroes.eval.workload import extract_integer
from heteroes.model.schema import build_parameter_schema
from heteroes.noise.contracts import ENGINE_V2
from heteroes.v3.model import file_manifest, load
from probe_strict_backend import PROMPTS, EXPECTED

def digest(t):
    return hashlib.sha256(t.detach().cpu().contiguous().numpy().tobytes()).hexdigest()

report = {'status': 'running', 'hardwareQualified': False, 'model': a.model_name,
          'sourceSha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
          'environment': {'python': platform.python_version(), 'torch': torch.__version__,
                          'transformers': transformers.__version__, 'platform': platform.platform(),
                          'gpu': torch.cuda.get_device_name(), 'computeCapability': list(torch.cuda.get_device_capability())},
          'noiseEngine': ENGINE_V2, 'seed': 7001, 'sigma': 1e-3, 'cases': []}
started = time.perf_counter()
files = file_manifest(a.model_path)
model, tok = load(a.model_path, files, 'cuda')
schema = build_parameter_schema(model)
snapshot = take_snapshot(model, schema)
parent = model_weights_sha256(model, schema)
report.update(modelFiles=files, parentSha256=parent, schemaHash=schema.hash)
engines = {}
for name, entry in (('original', 'strict_attention'), ('selected', None)):
    engines[name] = IntegerDecoderGraph(model, magnitude_bits=22, max_context=512, max_graph_bytes=4 * 1024**3)
    if entry:
        engines[name].kernels._attention_entry = entry
assert engines['original'].kernels is not engines['selected'].kernels
report['attentionEntries'] = {n: e.kernels._attention_entry for n, e in engines.items()}
report['kernelIdentity'] = engines['selected'].kernel_identity()
prompts = [tok(t, return_tensors='pt')['input_ids'].cuda() for t in PROMPTS]
width = max(x.shape[1] for x in prompts)
ids = torch.zeros((len(prompts), width), dtype=torch.long, device='cuda'); mask = torch.zeros_like(ids)
for i, x in enumerate(prompts):
    ids[i, -x.shape[1]:] = x[0]; mask[i, -x.shape[1]:] = 1
workloads = [('short8', ids, mask, 32, EXPECTED)]
if a.chat_workload:
    rows = json.loads(a.chat_workload.read_text())['models'][a.model_name]['rows'][:32]
    w = max(len(r['tokenIds']) for r in rows)
    cids = torch.zeros((len(rows), w), dtype=torch.long, device='cuda'); cmask = torch.zeros_like(cids)
    for i, r in enumerate(rows):
        cids[i, -len(r['tokenIds']):] = torch.tensor(r['tokenIds'], device='cuda'); cmask[i, -len(r['tokenIds']):] = 1
    workloads.append(('chat32x128', cids, cmask, 128, [None] * len(rows)))
    report['chatWorkloadSha256'] = hashlib.sha256(a.chat_workload.read_bytes()).hexdigest()
try:
    for state, seed, sigma in (('parent', None, 0), ('plus', 7001, 1e-3), ('minus', 7001, -1e-3), ('restored', None, 0)):
        case = {'state': state, 'results': {}}
        report['cases'].append(case)
        try:
            if seed is not None:
                perturb_model_(model, schema, seed, sigma, engine=ENGINE_V2)
            case['weightsSha256'] = model_weights_sha256(model, schema)
            for name, engine in engines.items():
                logits, caches = engine.forward_batch(prompts); del caches
                out = {'prefillLogitsSha256': digest(logits)}
                for label, wids, wmask, n, expected in workloads:
                    tokens = engine.generate(wids, attention_mask=wmask, max_new_tokens=n, eos_token_id=[], pad_token_id=0,
                                             repetition_penalty=1.0)[:, wids.shape[1]:].tolist()
                    texts = [tok.decode(r, skip_special_tokens=True) for r in tokens]
                    out[label] = {'tokens': tokens, 'tokensSha256': hashlib.sha256(json.dumps(tokens).encode()).hexdigest(),
                                  'rewards': [float(extract_integer(t) == e) if e is not None else None for t, e in zip(texts, expected)]}
                case['results'][name] = out
                engine.release_graph()
            o, s = case['results']['original'], case['results']['selected']
            if o != s:
                raise ValueError(f'{state}: selected attention differs from the original kernel')
            case['originalEqualsSelected'] = True
        finally:
            restore_from_snapshot_(model, schema, snapshot)
            case['restoreExact'] = model_weights_sha256(model, schema) == parent
            if not case['restoreExact']:
                raise ValueError('restore failed')
    if report['cases'][-1]['results'] != report['cases'][0]['results']:
        raise ValueError('restored parent differs from parent')
    report['status'] = 'ok'
except Exception as error:
    report.update(status='error', errorType=type(error).__name__, error=str(error)[:2000])
report['wallSeconds'] = time.perf_counter() - started
with a.out.open('x') as f:
    json.dump(report, f, indent=1); f.write('\n')
print(json.dumps({'status': report['status'], 'out': str(a.out), 'wallSeconds': report['wallSeconds']}))
raise SystemExit(int(report['status'] != 'ok'))
