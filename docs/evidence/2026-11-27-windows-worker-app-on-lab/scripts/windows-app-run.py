"""Short strict lab run with the packaged Windows Worker app (3060-quang-windows) beside the 5070 Ti coordinator:
Qwen2.5-0.5B (the app's pinned model), Countdown, population 8, 3 generations, strict_b22_v1, audits 25%."""
import json, os, sys
from pathlib import Path
EXP = Path.home() / "projects/heteroes/runtime/notebooks/experiments"
os.chdir(EXP)
for p in (str(EXP.parent.parent / "src"), str(EXP)):
    sys.path.insert(0, p)
import runner, tasks  # noqa
from heteroes.sdk import ESConfig, ESTrainer  # noqa
from heteroes.sdk_lab import Dataset, Lab, Model  # noqa
from heteroes.v3 import data as v3data  # noqa

import sys as _s
TAG = _s.argv[1] if len(_s.argv) > 1 else "windows-app-run"
OUT = Path.home() / "heteroes-experiments/winfix-20261127" / TAG
OUT.mkdir(parents=True, exist_ok=True)
COORD = "5070ti-nhan"
WORKERS = ["5070ti-nhan", "3060-quang-windows"] if TAG.endswith("audit") else ["3060-quang-windows"]
AUDIT = 0.5 if TAG.endswith("audit") else 0.25
lab = Lab.from_session()
splits = {k: [dict(r) for r in v] for k, v in v3data.build(tasks.countdown(), split_seed=42)["splits"].items()}
data = Dataset.from_rows(**splits, directory=OUT / "data")
model = Model.from_hf("Qwen/Qwen2.5-0.5B-Instruct", revision="7ae557604adf67be50417f59c2c2f167def9a775")
SCORER = {"name": "countdown", "config": {"numbersField": "nums", "targetField": "target"}}
args = ESConfig(model=model, dataset=data, population=8, batch_size=8, generations=3, alpha=5e-4, sigma=1e-3,
                max_new_tokens=128, eval_dtype="float16", decoder="strict_b22_v1", eval_chunk=8,
                validation_interval=25, audit_rate=AUDIT)
trainer = ESTrainer(args, code_dir=OUT / "code", scorer=SCORER)
state = OUT / "state.json"
if state.exists():
    run = lab.run(json.loads(state.read_text())["experimentId"])
else:
    run = runner.submit(trainer, lab, COORD, WORKERS, f"{TAG}-20261127", OUT / "offer")
    state.write_text(json.dumps({"experimentId": run.id}))
print("run", run.id, run.url, flush=True)
status = run.wait(every=20)
print("status", status, flush=True)
names = {d.worker_id: d.name for d in lab.devices()}
out = {"run": run.id, "status": status, "speed": runner.speed(run.id, names), "deviceTiming": runner.device_timing(run.id, names)}
(OUT / "result.json").write_text(json.dumps(out, indent=1, ensure_ascii=False))
print(json.dumps(out, ensure_ascii=False)[:3000], flush=True)
