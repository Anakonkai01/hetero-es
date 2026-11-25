"""What the experiment notebooks share: lab runs in segments, continuation between segments, and test scoring.

A notebook is rerunnable: each segment's lab experiment ID is kept in `state/<name>.json`, so running the notebook again
re-attaches to the segments already submitted and submits only the new ones listed in `decisions/<name>.json`
(each with its alpha, sigma, generations and the reason it was chosen). Test scores are computed once per checkpoint
and kept next to the run state.
"""

import json
import os
import time
import urllib.error
from pathlib import Path

HERE = Path(__file__).resolve().parent
WORK = Path.home() / "heteroes-experiments"
# A clean cache holds only the files a lab model may have (a cache filled by an earlier full download would be refused).
os.environ.setdefault("HF_HUB_CACHE", str(WORK / "hf-cache"))

TERMINAL = ("COMPLETED", "FAILED", "CANCELLED")


def _read(path, default):
    return json.loads(path.read_text()) if path.is_file() else default


class Experiment:
    def __init__(self, name):
        self.name = name
        self.dir = WORK / name
        self.dir.mkdir(parents=True, exist_ok=True)
        self.state_path = HERE / "state" / f"{name}.json"
        self.decisions_path = HERE / "decisions" / f"{name}.json"
        self.state = _read(self.state_path, {"segments": {}})

    def save(self):
        self.state_path.parent.mkdir(exist_ok=True)
        self.state_path.write_text(json.dumps(self.state, indent=1, ensure_ascii=False) + "\n")

    def segments(self, default):
        """The segments decided so far (decisions file), else the first one given by the notebook."""
        decided = _read(self.decisions_path, None)
        if decided is None:
            self.decisions_path.parent.mkdir(exist_ok=True)
            self.decisions_path.write_text(json.dumps([default], indent=1, ensure_ascii=False) + "\n")
            decided = [default]
        return decided


def submit(trainer, lab, coordinator, workers, name, directory, attempts=4, log=print):
    """`ESTrainer.submit` again after a dropped connection (the public tunnel resets a long request now and then).
    Waits first until the coordinator and workers are idle: the lab qualifies a device only while it runs nothing."""
    wanted = {coordinator, *workers}
    said = False
    while busy := [d.name for d in lab.devices() if d.name in wanted and d.busy]:
        if not said:
            log(f"  chờ {busy} rảnh…")
            said = True
        time.sleep(60)
    for attempt in range(attempts):
        try:
            return trainer.submit(lab, coordinator, workers, name=name, directory=directory, log=log)
        except (urllib.error.URLError, ConnectionError, TimeoutError) as error:
            if attempt == attempts - 1:
                raise
            log(f"  connection dropped ({error}); trying again")
            time.sleep(15)
        except Exception as error:  # noqa: BLE001 - only a failed qualification is retried, once
            # 25/11 14:15: the first qualification of a just-uploaded model failed (MODEL_PROBE_FAILED) right after a lab
            # restart; the same probe passed a few minutes later. Devices that already qualified are not probed again.
            if "did not qualify" not in str(error) or attempt >= 1:
                raise
            log(f"  {error}; qualifying again in a minute")
            time.sleep(60)


def continued_model(lab, run, base, out, model_id):
    """The next segment's model: the verified final weights of `run`, as a model of its own (uploaded to the lab)."""
    from heteroes.sdk_lab import Model

    out = Path(out)
    if not out.exists():
        run.derive_model(base.path, out)
    return Model.from_path(out, model_id)


def after_segment(lab, experiment, done, number):
    """The model holding the final weights of segment `number` (1-based) of `done` (derived once, then reused)."""
    _, run, model = done[number - 1]
    return continued_model(lab, run, model, experiment.dir / f"after-segment-{number:02d}",
                           f"{done[0][2].id}+{experiment.name}-s{number:02d}")


def run_segments(lab, experiment, base_model, make_trainer, segments, coordinator, workers, log=print, every=30):
    """Run (or re-attach to) every segment in order; returns [(segment, Run, Model)]. A later segment continues from
    the final weights of the one before it. `workers` may be a function returning the online devices to use."""
    model, done = base_model, []
    for number, segment in enumerate(segments, start=1):
        key = f"segment-{number:02d}"
        if number > 1:
            model = after_segment(lab, experiment, done, number - 1)
        entry = experiment.state["segments"].get(key)
        if entry is None:
            members = workers() if callable(workers) else workers
            log(f"{key}: α={segment['alpha']} σ={segment['sigma']} {segment['generations']} thế hệ trên {members}"
                f" — lý do: {segment['reason']}")
            from heteroes.canonical import canonical_json_hash

            trainer = make_trainer(model, segment)
            name = f"{experiment.name}-{key}"
            # one offer folder per exact configuration: a retry re-uses it, a changed configuration gets its own
            offer = experiment.dir / "offers" / f"{key}-{canonical_json_hash(trainer.lab_spec(name))[:12]}"
            run = submit(trainer, lab, coordinator, members, name, offer, log=log)
            experiment.state["segments"][key] = {"experimentId": run.id, "workers": members, **segment}
            experiment.save()
        else:
            run = lab.run(entry["experimentId"])
            log(f"{key}: đã có run {run.id}")
        status = run.wait(every=every)
        if status != "COMPLETED":
            # a segment stopped early counts only when its state records why (an explicit, written decision);
            # its newest verified recovery point is then the segment's result
            early = experiment.state["segments"][key].get("endedEarly")
            if status != "CANCELLED" or not early:
                raise RuntimeError(f"{key} ended {status}: {run.url}")
            log(f"{key}: dừng sớm ({status}) — {early}")
        done.append((segment, run, model))
    return done


def score_model(model_dir, rows, scorer, max_new_tokens, chunk=32, decoder="strict_b22_v1", device="cuda"):
    """Greedy answers of a model directory to `rows` with the run's decoder, and their scores (one per row)."""
    from heteroes.eval.precision import EvalModel
    from heteroes.study.evaluation import generate_rows
    from heteroes.v3.model import file_manifest, load
    from heteroes.v3.scoring import score

    model, tokenizer = load(model_dir, file_manifest(model_dir), device)
    evaluator = EvalModel(model, "float16")
    evaluator.refresh()
    evaluation = {"systemPrompt": None, "maxNewTokens": max_new_tokens, "decoder": decoder}
    generated = generate_rows(evaluator.model, tokenizer, rows, evaluation, chunk)
    outputs = [g["output"] for g in generated]
    full = {"kind": "declarative", "version": 1, "codeSha256": None, **scorer}
    mean, scores = score(full, outputs, rows)
    from heteroes.strict import strict_backend

    strict_backend.release(model)  # the strict engine keeps the model alive (and its GPU memory) until released
    del model, evaluator
    _free(device)
    return {"meanReward": mean, "scores": scores, "outputs": outputs,
            "truncated": sum(bool(g["truncated"]) for g in generated)}


def _free(device):
    if device == "cuda":
        import torch

        torch.cuda.empty_cache()


def test_report(experiment, label, generation, model_dir, rows, scorer, max_new_tokens, chunk=32):
    """Score `rows` once with this checkpoint (kept as test-<label>.json); a report `compare` reads."""
    from heteroes.canonical import canonical_json_hash

    path = experiment.dir / f"test-{label}.json"
    if path.is_file():
        return json.loads(path.read_text())
    result = score_model(model_dir, rows, scorer, max_new_tokens, chunk)
    report = {
        "rowsHash": canonical_json_hash(rows),
        "scorer": scorer,
        "model": str(model_dir),
        "checkpoints": [{"generation": generation, "split": "test", "count": len(rows), **result}],
    }
    path.write_text(json.dumps(report, ensure_ascii=False) + "\n")
    return report


def correct(report):
    scores = report["checkpoints"][0]["scores"]
    return sum(s == 1 for s in scores), len(scores)


def history(runs):
    """Training reward and validation per generation across segments (one continuous axis), and work per device.
    A segment that stopped early and was continued from an earlier point (`usedGenerations`) counts only up to it."""
    rewards, validation, work, offset = [], [], {}, 0
    for segment, run, _ in runs:
        result = run.results()
        used = segment.get("usedGenerations", len(result["generations"]))
        for g in result["generations"]:
            if g["generation"] < used:
                rewards.append((offset + g["generation"], g["rewardMean"]))
        for v in result["validation"]:
            if v["generation"] is not None and v["generation"] < used:
                validation.append((offset + v["generation"], v["reward"]))
        for worker, count in result["completedPerDevice"].items():
            work[worker] = work.get(worker, 0) + count
        offset += used
    return rewards, validation, work


def one_gpu_run(lab, experiment, make_trainer, model, segment, device, generations=6, log=print, every=30):
    """The same configuration on one GPU only, for a few generations: the 1-GPU reference of the speed table.
    Kept in the state like a segment, so running the notebook again re-attaches to it."""
    from heteroes.canonical import canonical_json_hash

    key = "one-gpu"
    entry = experiment.state.get(key)
    if entry is None:
        trainer = make_trainer(model, {**segment, "generations": generations})
        name = f"{experiment.name}-1gpu"
        offer = experiment.dir / "offers" / f"{key}-{canonical_json_hash(trainer.lab_spec(name))[:12]}"
        log(f"{key}: {generations} thế hệ chỉ trên {device}")
        run = submit(trainer, lab, device, [device], name, offer, log=log)
        experiment.state[key] = {"experimentId": run.id, "workers": [device], "generations": generations}
        experiment.save()
    else:
        run = lab.run(entry["experimentId"])
    status = run.wait(every=every)
    if status != "COMPLETED":
        raise RuntimeError(f"{key} ended {status}: {run.url}")
    return run


RUNS = Path.home() / ".local/share/heteroes-worker/agent-state/runs"  # the coordinator's ledgers (on its machine)


def speed(run_id, names):
    """From the coordinator's ledger, which records every candidate: seconds between weight updates per set of machines
    that scored that generation, candidates per machine, and audits (a candidate scored again by another machine).
    The first generation (model loading) has no previous update and is left out."""
    import collections
    import sqlite3

    path = RUNS / run_id / "ledger.sqlite"
    if not path.is_file():
        return None
    db = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    done = dict(db.execute("SELECT generation, recorded_at FROM generation_update"))
    who, per_device = collections.defaultdict(set), collections.Counter()
    for g, w in db.execute(
        "SELECT c.generation, a.worker_id FROM result r JOIN attempt a ON a.candidate_id = r.candidate_id "
        "AND a.attempt_number = r.attempt_number JOIN candidate c ON c.candidate_id = r.candidate_id"
    ):
        who[g].add(names.get(w, w))
        per_device[names.get(w, w)] += 1
    groups = collections.defaultdict(list)
    for g in sorted(done):
        if g - 1 in done and who.get(g):
            groups[" + ".join(sorted(who[g]))].append(done[g] - done[g - 1])
    audits, matched = db.execute("SELECT COUNT(*), COALESCE(SUM(matched), 0) FROM audit").fetchone()
    return {"groups": dict(groups), "perDevice": dict(per_device), "audits": audits, "matched": matched}


def finished(report, task):
    """Answers that reached their final answer within the token limit (a boxed number, or an <answer> tag), and how
    many of those are right: a gain that only comes from finishing more answers is not better reasoning."""
    import re

    checkpoint = report["checkpoints"][0]
    mark = (lambda t: "</answer>" in t) if task == "countdown" else (lambda t: re.search(r"\\boxed\{", t) is not None)
    done = [i for i, t in enumerate(checkpoint["outputs"]) if mark(t)]
    right = sum(1 for i in done if checkpoint["scores"][i] == 1)
    return {"finished": len(done), "rightAmongFinished": right, "count": len(checkpoint["outputs"]),
            "truncated": checkpoint.get("truncated")}
