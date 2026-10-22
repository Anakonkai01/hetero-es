"""Submit one declared system run through the researcher SDK, wait for it and save its public records (no credentials).

    HETEROES_GPU_ACCEPTANCE=1 PYTHONPATH=runtime/src python submit-run.py --gpu --out DIR --workers a,b --population 48 ...
"""
import argparse
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from heteroes.noise.contracts import ENGINE_V2
from heteroes.product.qualification_v3 import reference_rows
from heteroes.sdk import ESConfig, ESTrainer
from heteroes.sdk_lab import Dataset, Lab, Model
from heteroes.v3.model import registration_manifest

p = argparse.ArgumentParser()
p.add_argument('--gpu', action='store_true')
p.add_argument('--out', required=True)
p.add_argument('--name', required=True)
p.add_argument('--namespace', required=True)
p.add_argument('--workers', required=True)
p.add_argument('--coordinator', default='5070ti-nhan')
p.add_argument('--population', type=int, default=8)
p.add_argument('--generations', type=int, default=10)
p.add_argument('--batch', type=int, default=4)
p.add_argument('--tokens', type=int, default=32)
p.add_argument('--validation-interval', type=int, default=10)
p.add_argument('--no-wait', action='store_true')
a = p.parse_args()
if not a.gpu or os.environ.get('HETEROES_GPU_ACCEPTANCE') != '1':
    p.error('Explicit GPU authorization required')
out = Path(a.out)
out.mkdir(parents=True, exist_ok=True)
if (out / 'submission.json').exists():
    raise FileExistsError('already submitted into ' + str(out))
lab = Lab.from_session()
names = a.workers.split(',')
devices = [lab.device(n) for n in names]
bad = [d.name for d in devices if not (d.online and d.on and not d.busy and d.noise_version == ENGINE_V2)]
if bad:
    raise RuntimeError('not ready: ' + ','.join(bad))
model_path = Path.home() / '.local/share/heteroes-worker/models/7ae557604adf67be50417f59c2c2f167def9a775'
model_id = 'Qwen/Qwen2.5-0.5B-Instruct'
model = Model(model_id, str(model_path), model_path.name, 'REFERENCE',
              registration_manifest(model_path, model_id, model_path.name))
dataset = Dataset.from_rows(reference_rows(), directory=out / 'private-rows')
config = ESConfig(model=model, dataset=dataset, population=a.population, generations=a.generations,
                  batch_size=a.batch, alpha=.001, sigma=.001, antithetic=True, max_new_tokens=a.tokens,
                  eval_dtype='float32', decoder='hf_generate', eval_chunk=16,
                  validation_interval=a.validation_interval, candidate_seed_namespace=a.namespace)
declared = {'declaredAt': datetime.now(timezone.utc).isoformat(), 'name': a.name, 'coordinator': a.coordinator,
            'workers': names, 'population': a.population, 'generations': a.generations, 'batch': a.batch,
            'maxNewTokens': a.tokens, 'engine': ENGINE_V2, 'model': model_id,
            'modelManifestHash': model.manifest_hash, 'datasetInputHash': dataset.sha256}
(out / 'declared.json').write_text(json.dumps(declared, indent=2) + '\n')
run = ESTrainer(config, scorer={'name': 'last-integer'}).submit(
    lab, coordinator=a.coordinator, workers=names, name=a.name, directory=out / 'private-submit',
    log=lambda x: print(x, flush=True))
(out / 'submission.json').write_text(json.dumps({**declared, 'experimentId': run.id, 'url': run.url}, indent=2) + '\n')
print('RUN', run.id, flush=True)
if a.no_wait:
    raise SystemExit(0)
status = run.wait(every=10)
experiment = run.experiment()
keep = {k: experiment.get(k) for k in ('experimentId', 'status', 'createdAt', 'startedAt', 'completedAt',
                                       'completedGenerations', 'auditSummary', 'usageSummary', 'validationScore')}
(out / 'final.json').write_text(json.dumps(keep, indent=2) + '\n')
(out / 'timeline.json').write_text(json.dumps(run.timeline(), indent=2) + '\n')
(out / 'results.json').write_text(json.dumps(run.results(), indent=2) + '\n')
print('DONE', run.id, status, flush=True)
