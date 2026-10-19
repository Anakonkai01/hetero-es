"""
A Recipe v3 experiment on one machine: the coordinator, its workers (threads, each with its own copy of the model) and the
real HTTP protocol on the loopback interface, exactly the code a lab runs, without the product around it.

    run_local(config, out_dir, device="cpu", workers=1)

`config` is a plain dict (see `heteroes.sdk.ESConfig`, which builds it). The run directory receives the recipe, the plan,
the dataset document, the ledger (texts included), the published weights and an event log. A Python scorer may be used
here: this coordinator is the researcher's own (ADR-008 decision 4).
"""

import hashlib
import json
import shutil
import threading
import time
from pathlib import Path

from heteroes.canonical import canonical_json_hash


def _write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=1, sort_keys=True) + "\n", encoding="utf-8")


def _scorer_spec(config):
    scorer = config["scorer"]
    if scorer["kind"] == "python":
        from heteroes.v3.run import load_python_scorer

        function, digest = load_python_scorer(scorer["path"], scorer["function"])
        spec = {
            "kind": "python",
            "name": scorer["name"],
            "version": scorer["version"],
            "codeSha256": digest,
            "config": {},
        }
        return spec, function
    spec = {"kind": "declarative", "name": scorer["name"], "version": scorer.get("version", 1), "codeSha256": None}
    return spec | {"config": scorer.get("config", {})}, None


def _coefficient_rule(config):
    """(rule name for the plan, loaded function or None): a string, or {"kind": "python", "path", "function"}."""
    rule = config.get("coefficientRule", "zscore@1")
    if isinstance(rule, dict) and rule.get("kind") == "python":
        from heteroes.v3.coefficients import python_rule
        from heteroes.v3.run import load_python_scorer

        function, digest = load_python_scorer(rule["path"], rule["function"])
        return python_rule(digest), function
    return rule, None


def prepare(config, out_dir, device="cpu", initial_adapter=None):
    """
    Load the model and data, build and write the documents. Returns everything the run needs. `initial_adapter` (a LoRA
    run only) is a pinned adapter file copied into the run and loaded instead of one made from `adapterSeed`: the seed
    gives other bytes on another operating system, the file does not.
    """
    from heteroes.manifest import generation_config_sha256
    from heteroes.model.lora import create_initial_adapter
    from heteroes.model.lora import trainable_schema as adapter_schema
    from heteroes.model.schema import build_parameter_schema
    from heteroes.v3 import data as v3data
    from heteroes.v3.model import file_manifest, load, trainable_schema
    from heteroes.v3.run import RecipeV3Run, build_documents

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    model_path = Path(config["model"]["path"])
    files = file_manifest(model_path)
    # a local model has no hub commit: its revision is derived from the hashes of its files (40 hex digits)
    revision = config["model"].get("revision") or canonical_json_hash(files)[:40]
    model, tokenizer = load(model_path, files, device)
    rows = v3data.read_rows(config["data"]["path"], config["data"].get("promptField", "prompt"))
    dataset = v3data.build(rows, split_seed=config["data"].get("splitSeed", 42))
    space = config.get("weightSpace") or {"kind": "full"}
    adapter_file = adapter_sha = None
    if initial_adapter is not None and space["kind"] != "lora":
        raise ValueError("an initial adapter is only for a LoRA weight space")
    if space["kind"] == "lora":
        adapter_file = out / "initial-adapter.bin"
        if initial_adapter is not None:
            shutil.copyfile(initial_adapter, adapter_file)
            with adapter_file.open("rb") as stream:
                adapter_sha = hashlib.file_digest(stream, "sha256").hexdigest()
            schema = trainable_schema(model, {**space, "initialAdapterSha256": adapter_sha}, adapter_file)
        else:
            adapter_sha = create_initial_adapter(model, space, space.get("adapterSeed", 0), adapter_file)
            schema = adapter_schema(model)
    elif space["kind"] == "subset":
        from heteroes.model.schema import select_parameters

        schema = select_parameters(build_parameter_schema(model), space["include"])
    else:
        schema = build_parameter_schema(model)
    scorer_spec, python_scorer = _scorer_spec(config)
    rule, coefficient_function = _coefficient_rule(config)
    recipe, plan = build_documents(
        {**config, **config["data"], "scorerSpec": scorer_spec, "coefficientRule": rule},
        model_files=files,
        revision=revision,
        schema_hash=schema.hash,
        generation_config_sha256=generation_config_sha256(model.generation_config.to_dict()),
        dataset=dataset,
        adapter_sha256=adapter_sha,
    )
    for name, value in (("recipe.json", recipe), ("plan.json", plan), ("dataset.json", dataset)):
        _write_json(out / name, value)
    run = RecipeV3Run(recipe, plan)

    def worker_model():
        worker, worker_tokenizer = load(model_path, files, device)
        return worker, worker_tokenizer, trainable_schema(worker, recipe["weightSpace"], adapter_file)

    return {
        "run": run,
        "model": model,
        "tokenizer": tokenizer,
        "schema": schema,
        "dataset": dataset,
        "python_scorer": python_scorer,
        "coefficient_function": coefficient_function,
        "worker_model": worker_model,
        "out": out,
    }


def run_local(
    config, out_dir, device="cpu", workers=1, experiment_id="local", log=None, timeout_seconds=None, audit_rate=0.05
):
    """
    Run the experiment to its end; returns the generation summaries. Events go to `<out_dir>/events.jsonl` and `log`.
    `timeout_seconds` bounds each generation (None: no bound, only the coordinator's stall detection).
    """
    from heteroes.coordinator import Coordinator
    from heteroes.executor import CandidateExecutor
    from heteroes.http_transport import HttpClient
    from heteroes.ledger import Ledger
    from heteroes.model.loading import check_recipe_selftest
    from heteroes.v3.run import make_scorer
    from heteroes.worker_runtime import WorkerRuntime

    ready = prepare(config, out_dir, device)
    run, out = ready["run"], ready["out"]
    check_recipe_selftest(run, device)
    events = (out / "events.jsonl").open("a", encoding="utf-8")
    lock = threading.Lock()

    def record(event):
        with lock:
            events.write(json.dumps(event, sort_keys=True) + "\n")
            events.flush()
        if log is not None:
            log(event)

    ledger = Ledger(out / "ledger.sqlite", enforce_chain=True)
    coordinator = Coordinator(
        ready["model"],
        ready["schema"],
        run,
        ledger,
        out / "published",
        experiment_id=experiment_id,
        candidates=run.plan["population"],
        alpha=run.plan["alpha"],
        log=record,
        dataset=ready["dataset"],
        antithetic=run.antithetic,
        coefficient_rule=run.coefficient_rule,
        coefficient_function=ready["coefficient_function"],
        audit_workers=[f"local-{index}" for index in range(workers)],
        audit_rate=audit_rate,
        score=make_scorer(run, ready["dataset"], ready["python_scorer"]),
        poll_seconds=0.05,
        timeout_seconds=timeout_seconds,
    )
    coordinator.start()
    stop, threads = threading.Event(), []
    try:
        for index in range(workers):
            model, tokenizer, schema = ready["worker_model"]()
            (out / f"cache-{index}").mkdir(exist_ok=True)
            executor = CandidateExecutor(
                model, tokenizer, schema, run, dataset=ready["dataset"], return_completions=True
            )
            runtime = WorkerRuntime(
                f"local-{index}",
                HttpClient(coordinator.url),
                executor,
                out / f"cache-{index}",
                log=record,
                poll_seconds=0.05,
            )
            thread = threading.Thread(target=runtime.run, args=(stop,), daemon=True, name=f"local-{index}")
            thread.start()
            threads.append(thread)
        started = time.time()
        summaries = coordinator.run(run.plan["generations"])
        record({"event": "run_finished", "t": time.time(), "seconds": time.time() - started})
        return summaries
    finally:
        stop.set()
        for thread in threads:
            thread.join(timeout=30)
        coordinator.stop()
        ledger.close()
        events.close()
