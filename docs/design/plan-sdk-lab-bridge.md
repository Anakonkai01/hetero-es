# Submit an experiment to the lab with the Python SDK

The SDK supports local execution through `ESTrainer.train()` and managed execution through
`ESTrainer.submit()`. Use a reachable lab, an approved workspace, and the names or IDs of the devices assigned to
that workspace. The [researcher notebook](../../runtime/notebooks/researcher.ipynb) shows data preparation, a pinned model,
reward/sampler definitions and on-lab submission. Check [lab availability](../HANDOFF.md) before connecting.

## Managed submission

Use `Lab.connect()` for a lab with local username/password auth. `Lab.from_session()` loads a private session
saved by [lab-login.py](../../scripts/lab-login.py). A client with a valid lab access token and workspace ID can also
pass them directly to `Lab(url, token, workspace)`.

```python
from heteroes.sdk import ESConfig, ESTrainer
from heteroes.sdk_lab import Dataset, Lab, Model

lab = Lab.connect("https://your-lab.example", workspace="research")
print(lab.devices())

# Supply a pinned repository revision and populated prompt/answer rows.
model = Model.from_hf(model_repo, revision=model_commit)
dataset = Dataset.from_rows(train=train_rows, validation=validation_rows, test=test_rows)
config = ESConfig(model=model, dataset=dataset)
trainer = ESTrainer(config, scorer={"name": "answer-line-last-number"})
run = trainer.submit(lab, coordinator=coordinator_id, workers=worker_ids, name="research run")
print(run.id, run.status())
```

Submission registers the inputs, qualifies the selected devices by default, and queues the experiment. The local
`lab-offer.json` receipt lets a retry reuse completed registration steps and the experiment. Keep its directory
bound to the same inputs. An operator approves devices and their owners enable contribution. Select `strict_b22_v1`
with `eval_dtype="float16"` for a strict SDK run and choose a coordinator GPU separate from the worker GPUs. The SDK's default decoder is
`hf_generate`.

`run.watch()` draws the notebook dashboard until the run ends or the cell is interrupted. Use `run.wait()` to
wait for a terminal status, or `lab.run(experiment_id)` to reconnect. `run.results()` reads the lab's retained
timeline and validation events. If it reports `partialTimeline`, use the coordinator's ledger for complete per-candidate
and per-generation records. See [data ownership](lab-server-architecture.md#b-q2-where-data-and-backups-live).

[SDK implementation](../../runtime/src/heteroes/sdk_lab.py) · [SDK lab tests](../../runtime/tests/v3/test_sdk_lab.py) ·
[Local Recipe v3 experiments](../../runtime/docs/v3-local-runs.md)
