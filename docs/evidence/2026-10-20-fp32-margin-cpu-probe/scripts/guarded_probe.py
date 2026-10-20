"""Scratch-only FP32 generation with a CPU FP64 reference for small processed-score margins."""
import argparse
import copy
from functools import wraps
import json
import os
from pathlib import Path
import time

import torch
from torch.utils._python_dispatch import TorchDispatchMode

from heteroes.eval.candidate import model_weights_sha256
from heteroes.executor import CandidateExecutor
from heteroes.manifest import CandidateDescriptor
from heteroes.model.weights_io import load_weights_
from heteroes.runtime_info import environment_info
from heteroes.v3.data import open_dataset
from heteroes.v3.model import load, trainable_schema
from heteroes.v3.run import RecipeV3Run
from heteroes.worker_api import completions_sha256
from transformers import LogitsProcessorList
from margin_guard import MarginGuard


class FullPrecision(TorchDispatchMode):
    def __torch_dispatch__(self, func, types, args=(), kwargs=None):
        kwargs = kwargs or {}
        if func == torch.ops.aten._to_copy.default and kwargs.get('dtype') == torch.float32:
            kwargs = {**kwargs, 'dtype': torch.float64}
        return func(*args, **kwargs)


class ReferenceComplete(Exception):
    pass


p = argparse.ArgumentParser()
p.add_argument('--gpu', action='store_true', required=True)
p.add_argument('--model', required=True)
p.add_argument('--inputs', required=True)
p.add_argument('--baseline', required=True)
p.add_argument('--out', required=True)
a = p.parse_args()
assert os.environ.get('HETEROES_GPU_ACCEPTANCE') == '1'
root = Path(a.inputs)
recipe = json.loads((root / 'recipe.json').read_text())
plan = json.loads((root / 'plan.json').read_text())
candidate = json.loads((root / 'candidate.json').read_text())
baseline = json.loads(Path(a.baseline).read_text())
assert baseline['descriptor'] == candidate['descriptor']
capture = baseline['results'][0]['capture']
run = RecipeV3Run(recipe, plan)
desc = CandidateDescriptor(**candidate['descriptor'])
model, tok = load(a.model, recipe['model']['files'], 'cuda')
schema = trainable_schema(model, recipe['weightSpace'])
assert schema.hash == recipe['schemaHash']
load_weights_(model, schema, root / 'parent-fp16.bin', desc.parent_weights_sha256)
assert model_weights_sha256(model, schema) == desc.parent_weights_sha256
data = open_dataset(root / 'dataset.json')
executor = CandidateExecutor(model, tok, schema, run, dataset=data, return_completions=True)
executor.set_generation(desc.generation, run.context(data, desc.generation))
results = []
timings = {}
original_generate = executor._eval.model.generate
finished = {}


def trace(*args, **kwargs):
    assert kwargs['input_ids'].cpu().tolist() == capture['inputIds']
    assert kwargs['attention_mask'].cpu().tolist() == capture['attentionMask']
    assert model_weights_sha256(model, schema) == capture['perturbedFp16Sha256']
    torch.set_num_threads(4)
    reference = None
    initial_length = kwargs['input_ids'].shape[1]
    initial_mask = kwargs['attention_mask'].cpu()
    torch.cuda.synchronize()
    started = time.perf_counter()
    control = original_generate(*args, **kwargs)
    torch.cuda.synchronize()
    timings['primaryFp32GenerateSeconds'] = time.perf_counter() - started
    finished['controlNewTokenIds'] = control[:, initial_length:].cpu().tolist()
    finished['controlSha256'] = completions_sha256(tok.batch_decode(control[:, initial_length:], skip_special_tokens=True))

    def recompute(row, prefix):
        nonlocal reference
        if reference is None:
            started = time.perf_counter()
            reference = copy.deepcopy(model).to('cpu').double()
            timings['createCpuFp64ReferenceSeconds'] = time.perf_counter() - started
            assert all(t.device.type == 'cpu' and t.dtype == torch.float64 for t in reference.parameters())
            forward = reference.forward

            @wraps(forward)
            def precise_forward(*args, **kwargs):
                with FullPrecision():
                    return forward(*args, **kwargs)

            reference.forward = precise_forward
        step = prefix.shape[1] - initial_length
        mask = torch.cat([initial_mask[row:row + 1], torch.ones((1, step), dtype=initial_mask.dtype)], dim=-1)
        started = time.perf_counter()
        with torch.no_grad():
            reply = reference.generate(input_ids=prefix.cpu(), attention_mask=mask, max_new_tokens=1,
                                       do_sample=False, return_dict_in_generate=True, output_scores=True)
        elapsed = time.perf_counter() - started
        scores = reply.scores[0]
        values, indices = scores.topk(2, dim=-1)
        result = {'row': row, 'step': step, 'seconds': elapsed,
                  'topTwoIds': indices.tolist()[0], 'topTwoScores': values.tolist()[0],
                  'nextTokenId': int(reply.sequences[0, -1])}
        results.append(result)
        print(json.dumps(result), flush=True)
        return scores[0]

    torch.cuda.synchronize()
    started = time.perf_counter()
    reply = original_generate(*args, **kwargs, logits_processor=LogitsProcessorList([MarginGuard(0.01, recompute)]))
    torch.cuda.synchronize()
    timings['guardedGenerateSecondsIncludingLazyReferenceCreation'] = time.perf_counter() - started
    finished['guardedNewTokenIds'] = reply[:, initial_length:].cpu().tolist()
    return reply


executor._eval.model.generate = trace
texts = list(executor(desc))
assert model_weights_sha256(model, schema) == desc.parent_weights_sha256
finished['guardedSha256'] = completions_sha256(texts)
finished['texts'] = texts
out = {'environment': environment_info('cuda'), 'cpuThreads': torch.get_num_threads(),
       'descriptor': desc.to_dict(), 'referenceDevice': 'cpu', 'referenceDtype': 'float64',
       'marginThreshold': 0.01, 'timings': timings, 'results': results, 'finished': finished,
       'restoredParentSha256': desc.parent_weights_sha256,
       'limits': 'One candidate only; empirical margin threshold, no universal error bound or release acceptance.'}
with open(a.out, 'x') as f:
    json.dump(out, f, indent=1)
    f.write('\n')
