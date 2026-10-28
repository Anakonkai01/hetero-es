"""Exact historical candidate inputs, explicitly new decoder identity, no installed runtime changes."""
import argparse
import copy
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path

import torch

from heteroes.canonical import canonical_json_hash
from heteroes.catalog import CPU_GUARD_DECODER
from heteroes.eval import cpu_guard
from heteroes.eval.candidate import model_weights_sha256, tensors_sha256
from heteroes.executor import CandidateExecutor
from heteroes.manifest import CandidateDescriptor
from heteroes.model.weights_io import load_weights_
from heteroes.runtime_info import environment_info
from heteroes.v3.data import open_dataset
from heteroes.v3.model import load, trainable_schema
from heteroes.v3.run import RecipeV3Run
from heteroes.worker_api import completions_sha256

p = argparse.ArgumentParser()
p.add_argument('--gpu', action='store_true', required=True)
p.add_argument('--model', required=True)
p.add_argument('--inputs', required=True)
p.add_argument('--out', required=True)
a = p.parse_args()
assert os.environ.get('HETEROES_GPU_ACCEPTANCE') == '1'
root = Path(a.inputs)
recipe = json.loads((root / 'recipe.json').read_text())
plan = json.loads((root / 'plan.json').read_text())
old_recipe_hash = canonical_json_hash(recipe)
recipe['evaluation']['decoder'] = CPU_GUARD_DECODER
plan['recipeHash'] = canonical_json_hash(recipe)
run = RecipeV3Run(recipe, plan)
old = CandidateDescriptor(**json.loads((root / 'candidate.json').read_text())['descriptor'])
assert old.recipe_hash == old_recipe_hash
desc = replace(old, recipe_hash=run.hash, experiment_id='cpu-guard-diagnostic')
model, tok = load(a.model, recipe['model']['files'], 'cuda')
schema = trainable_schema(model, recipe['weightSpace'])
assert schema.hash == recipe['schemaHash']
load_weights_(model, schema, root / 'parent-fp16.bin', desc.parent_weights_sha256)
data = open_dataset(root / 'dataset.json')
executor = CandidateExecutor(model, tok, schema, run, dataset=data, return_completions=True)
executor.set_generation(desc.generation, run.context(data, desc.generation))
original = cpu_guard.guarded_generate_ids
captures = []


def capture(*args, **kwargs):
    primary = args[0]
    assert all(p.dtype == torch.float32 and p.device.type == 'cuda' for p in primary.parameters())
    values = {'inputIds': kwargs['input_ids'].cpu().tolist(),
              'attentionMask': kwargs['attention_mask'].cpu().tolist(),
              'evaluationFp32Sha256': tensors_sha256(list(primary.parameters())),
              'perturbedFp16Sha256': model_weights_sha256(model, schema)}
    ids, stats = original(*args, **kwargs)
    values['stats'] = stats
    values['newTokenIds'] = ids[:, kwargs['input_ids'].shape[1]:].cpu().tolist()
    assert all(p.dtype == torch.float32 and p.device.type == 'cuda' for p in primary.parameters())
    captures.append(values)
    return ids, stats


cpu_guard.guarded_generate_ids = capture
results = []
cases = json.loads((root / 'generation10-candidates.json').read_text())
cases.append(cases[5])
for repeat, case in enumerate(cases):
    desc = replace(desc, index=case['index'], seed=case['seed'], sign=case['sign'])
    torch.cuda.reset_peak_memory_stats()
    texts = list(executor(desc))
    sha = completions_sha256(texts)
    assert model_weights_sha256(model, schema) == desc.parent_weights_sha256
    result = {'repeat': repeat, 'descriptor': desc.to_dict(), 'texts': texts, 'sha256': sha, 'capture': captures[-1],
              'availableCpuRamBytesAfterRestore': cpu_guard.available_memory_bytes(),
              'peakGpuAllocatedBytes': torch.cuda.max_memory_allocated(),
              'restoredParentSha256': desc.parent_weights_sha256, 'candidateTiming': executor.last_timing}
    results.append(result)
    print(json.dumps({'repeat': repeat, 'sha256': sha, 'stats': captures[-1]['stats']}), flush=True)
out = {'environment': environment_info('cuda'), 'cpuThreads': torch.get_num_threads(),
       'decoderSourceSha256': hashlib.sha256(Path(cpu_guard.__file__).read_bytes()).hexdigest(),
       'oldRecipeHash': old_recipe_hash, 'recipe': recipe, 'plan': plan, 'descriptor': desc.to_dict(),
       'results': results, 'limits': 'Eight candidates on one historical parent plus a repeated c5; newly identified decoder; not managed acceptance.'}
with open(a.out, 'x') as f:
    json.dump(out, f, indent=1)
    f.write('\n')
