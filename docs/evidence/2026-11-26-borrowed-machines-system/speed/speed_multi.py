"""E4 config (Qwen2.5-1.5B Countdown, pop 32, 384 tokens, strict_b22_v1, backup every 10 gens) on several GPUs,
same model as the 1-GPU speed run 6131a0ad (after-segment-01 of e4-countdown-qwen15). Usage: speed_multi.py KEY GENS DEV..."""
import json, os, statistics, sys, time
from pathlib import Path
EXP = Path.home() / "projects/heteroes/runtime/notebooks/experiments"
os.chdir(EXP)
for p in (str(EXP.parent.parent / "src"), str(EXP)):
    sys.path.insert(0, p)
import runner, tasks  # noqa
from heteroes.sdk import ESConfig, ESTrainer  # noqa
from heteroes.sdk_lab import Dataset, Lab, Model  # noqa
from heteroes.v3 import data as v3data  # noqa
from heteroes.canonical import canonical_json_hash  # noqa

key, gens, devices = sys.argv[1], int(sys.argv[2]), sys.argv[3:]
COORD = "5070ti-nhan"
lab = Lab.from_session()
base_exp = runner.Experiment("e4-countdown-qwen15")
exp = runner.Experiment("e4-speed-backup10")
exp.state_path = Path.home() / "heteroes-experiments/borrowed-20261126/speed-state.json"  # keep the repo source tree unchanged
exp.state = json.loads(exp.state_path.read_text())
splits = {k: [dict(r) for r in v] for k, v in v3data.build(tasks.countdown(), split_seed=42)["splits"].items()}
data = Dataset.from_rows(**splits, directory=base_exp.dir / "data")
base = Model.from_hf('Qwen/Qwen2.5-1.5B-Instruct', revision='989aa7980e4cf806f80c7fef2b1adb7bc71aa306')
segs = base_exp.segments(None)
runs = runner.run_segments(lab, base_exp, base, None, segs, COORD, [])  # re-attach only
model = runs[-1][2]
seg = segs[-1]
SCORER = {"name": "countdown", "config": {"numbersField": "nums", "targetField": "target"}}
args = ESConfig(model=model, dataset=data, population=32, batch_size=32, generations=gens, alpha=seg["alpha"],
                sigma=seg["sigma"], max_new_tokens=384, eval_dtype="float16", decoder="strict_b22_v1", eval_chunk=32,
                validation_interval=25, audit_rate=0.05)
trainer = ESTrainer(args, code_dir=base_exp.dir / "code", scorer=SCORER)
entry = exp.state.get(key)
if entry is None:
    name = f"e4-speed-{key}"
    offer = exp.dir / "offers" / f"{key}-{canonical_json_hash(trainer.lab_spec(name))[:12]}"
    print(f"{key}: {gens} gens on {devices}", flush=True)
    run = runner.submit(trainer, lab, COORD, devices, name, offer)
    exp.state[key] = {"experimentId": run.id, "workers": devices, "generations": gens}
    exp.save()
else:
    run = lab.run(entry["experimentId"])
print("run", run.id, run.url, flush=True)
status = run.wait(every=30)
print("status", status, flush=True)
names = {d.worker_id: d.name for d in lab.devices()}
out = {"key": key, "run": run.id, "status": status, "devices": devices,
       "phases": runner.phases(run.id), "speed": runner.speed(run.id, names), "deviceTiming": runner.device_timing(run.id, names)}
Path.home().joinpath("heteroes-experiments/borrowed-20261126", f"speed-{key}.json").write_text(json.dumps(out, indent=1, ensure_ascii=False))
print(json.dumps(out, ensure_ascii=False), flush=True)
