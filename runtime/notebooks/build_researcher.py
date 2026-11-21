"""Write researcher.ipynb (cells only, no outputs). Run: .venv-notebook/bin/python runtime/notebooks/build_researcher.py"""

from pathlib import Path

import nbformat as nbf

md, code = nbf.v4.new_markdown_cell, nbf.v4.new_code_cell

cells = [
    md("""# You are the researcher: an ES experiment on a shared GPU lab

This notebook is the way to create an experiment on a HeteroES lab. You bring the model, the rows, the reward and, if
you like, the order in which rows are seen; the lab brings the GPUs of its members, schedules the work, audits it and
keeps a ledger from which every update can be recomputed.

| Step | What you write | What the lab does with it |
|---|---|---|
| 1. Connect | your lab account | a session in memory (12 hours), nothing saved |
| 2. Data | any loader: the hub, files, a database | freezes the rows (content hash), uploads them |
| 3. Model | a hub id | pins the commit and every file's SHA-256; each GPU downloads and checks it |
| 4. Reward / sampler | Python functions in a cell | freezes their source (SHA-256); they run on the coordinator only |
| 5. Settings | `ESConfig` | a recipe whose hash names the experiment |
| 6. Submit, watch | `submit`, `watch` | qualifies the GPUs for the model, queues the run, streams its progress |

Use Python 3.12 and the SDK matching your lab. On a lab that serves the notebook and SDK together, download its SDK
wheel from the lab's Notebook page. For a lab built from this checkout, install from the repository root:

```
python -m pip install -e ./runtime huggingface_hub datasets
```"""),
    md("""## 1. Connect

Enter the URL of a reachable lab that uses local account authentication. Choose a workspace your account can access.
The password prompt is private. Device owners decide when their devices are ON."""),
    code("""from heteroes.sdk import ESConfig, ESTrainer
from heteroes.sdk_lab import Dataset, Lab, Model

lab_url = input("Lab URL: ").strip()
workspace = input("Workspace name (Enter for your first workspace): ").strip() or None
lab = Lab.connect(lab_url, workspace=workspace)
for d in lab.devices():
    print(f"{d.name:16} {d.gpu:28} {d.vram_gb:5.1f} GB  online={d.online}  ON={d.on}  busy={d.busy}")"""),
    md("""## 2. Data: your own loader

Anything that produces rows works. A row is a dict with a text `prompt`; every other column is passed to your reward as
it is. Here: GSM8K from the hub, the final number of the solution as `answer`, and the training rows **sorted by
length** so that a sampler can walk from short (easier) to long questions. The official test split stays the test split;
500 training rows are held out for validation."""),
    code("""from datasets import load_dataset

gsm8k = load_dataset("openai/gsm8k", "main", revision="740312add88f781978c0658806c59bc2815b9866")

def rows_of(split):
    out = []
    for item in split:
        out.append({
            "prompt": item["question"] + "\\nGive the final answer as a number on the last line.",
            "answer": item["answer"].split("####")[-1].strip().replace(",", ""),
            "length": len(item["question"]),
        })
    return out

train = rows_of(gsm8k["train"])
validation, train = train[:500], sorted(train[500:], key=lambda r: r["length"])
test = rows_of(gsm8k["test"])
data = Dataset.from_rows(train=train, validation=validation, test=test)
data.counts"""),
    md("""## 3. Model

`Model.from_hf` downloads the safe files only (no code, no pickles) at one commit and pins each file's SHA-256. On the
lab it is a *reference*: every GPU downloads the same commit from the hub and checks every file, so no private network
is needed. (`Model.from_path(dir, id)` sends a model of your own instead; that needs the lab's private network.)"""),
    code("""model = Model.from_hf("Qwen/Qwen2.5-0.5B-Instruct", revision="7ae557604adf67be50417f59c2c2f167def9a775")
model"""),
    md("""## 4. Reward and sampler: Python functions

A reward scores one candidate's answers: one number per row, the candidate's reward is their mean. A sampler chooses the
row numbers of each generation; here a curriculum that walks the length-sorted rows from the start. Both are frozen from
their own source, so **write their imports inside them**: they run on the coordinator, not in this notebook (the SDK
says so if a function reads something from the notebook). A changed function is a different experiment."""),
    code('''def last_number(completions, rows):
    import re
    scores = []
    for text, row in zip(completions, rows):
        numbers = re.findall(r"-?\\d+(?:\\.\\d+)?", text.replace(",", ""))
        scores.append(float(bool(numbers) and float(numbers[-1]) == float(row["answer"])))
    return scores


def curriculum(generation, size, train_rows, seed):
    """The rows are sorted by question length: generation g reads the g-th window, wrapping around."""
    start = (generation * size) % train_rows
    return [(start + i) % train_rows for i in range(size)]


# try the reward on two made-up answers before sending it anywhere
last_number(["... so the answer is\\n72", "I think 71"], [{"answer": "72"}, {"answer": "72"}])'''),
    md("""## 5. Settings: batch and chunks from what each GPU measured

*Batch* is how many questions each candidate answers per generation: more questions, less luck in the ranking. *Chunk*
is how many of them go through the GPU in one call: a larger chunk is faster but needs more memory. Each GPU measured
its memory per chunk for this model when it qualified; `suggest` scales that to your answer length and gives each GPU
the largest chunk it holds (a GPU not measured yet gets a chunk from its memory size, and the note says so).
Enter approved device names or worker IDs from section 1. The example uses the SDK's `hf_generate` decoder.
A strict B22 run requires `decoder="strict_b22_v1"`, `eval_dtype="float16"` and a coordinator GPU distinct from
the worker GPUs."""),
    code("""COORDINATOR = input("Coordinator name or ID: ").strip()
WORKERS = [name.strip() for name in input("Worker names or IDs (comma-separated): ").split(",") if name.strip()]
hint = lab.suggest(model, data, max_new_tokens=256, devices=WORKERS)
print(hint)"""),
    code("""args = ESConfig(
    model=model,
    dataset=data,
    population=32,               # candidates per generation
    generations=30,
    sigma=1e-3,                  # size of each candidate's noise
    alpha=5e-4,                  # step size of the update
    coefficient_rule="centered-rank@1",
    batch_size=hint.batch_size,
    eval_chunk=hint.eval_chunk,
    eval_chunks=hint.eval_chunks,
    max_new_tokens=256,
    validation_interval=10,      # score the validation rows every 10 generations
)
trainer = ESTrainer(args, reward_func=last_number, sampler_func=curriculum)"""),
    md("""## 6. Submit and watch

`coordinator` is the GPU that keeps the ledger and runs your reward; `workers` evaluate candidates. A GPU not yet
qualified for this model is qualified first and must be ON. Run the submission cell when you have permission to use
the selected devices. `submit` returns once the experiment is queued. Interrupting `watch` stops the dashboard while
the run continues. For a long run, `partialTimeline` in `results()` signals that the complete history is in the
coordinator's ledger."""),
    code("""run = trainer.submit(lab, coordinator=COORDINATOR, workers=WORKERS, name="GSM8K curriculum")
run.url"""),
    code("""run.watch()"""),
    code("""run.results()"""),
    md("""## What this notebook does not show

- That ES improves GSM8K for this model: the project's claim is the system (correct, reproducible, measurable runs on
  mismatched GPUs), not a learning result. Thirty generations of a 0.5B model are expected to move accuracy by very
  little, if at all.
- Exactness of a particular run: that is the parity check (the ledger replayed and generations regenerated on another
  GPU), recorded with each run's evidence."""),
]

notebook = nbf.v4.new_notebook(cells=cells, metadata={"kernelspec": {"name": "python3", "display_name": "Python 3"}})
nbf.write(notebook, Path(__file__).with_name("researcher.ipynb"))
