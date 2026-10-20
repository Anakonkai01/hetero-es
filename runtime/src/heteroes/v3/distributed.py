"""Self-hosted v3 coordinator and workers; only the coordinator loads researcher Python code."""

import json
import os
from pathlib import Path
import shutil
import signal
import sys
import threading
import time

from heteroes.canonical import canonical_json_hash
from heteroes.product.files import write_json


def _token(name):
    value = os.environ.get(name)
    if not value:
        raise ValueError(f"Set {name} to the shared secret in the environment")
    return value


def validate_inputs(inputs, expected_recipe_hash=None):
    from heteroes.v3.data import verify
    from heteroes.v3.run import RecipeV3Run

    if not isinstance(inputs, dict) or set(inputs) != {"formatVersion", "recipe", "plan", "dataset"}:
        raise ValueError("Only pinned recipe, plan and dataset documents may be transferred")
    if inputs["formatVersion"] != 1:
        raise ValueError("Unknown distributed input format")
    run = RecipeV3Run(inputs["recipe"], inputs["plan"])
    if expected_recipe_hash is not None and run.hash != expected_recipe_hash:
        raise ValueError("The coordinator recipe differs from the expected recipe hash")
    verify(inputs["dataset"])
    for field in ("contentHash", "splitHashes"):
        if inputs["dataset"][field] != run.recipe["data"][field]:
            raise ValueError("Dataset identity differs from the pinned recipe")
    return run


def _signals(stop):
    previous = {}
    if threading.current_thread() is threading.main_thread():
        for number in (signal.SIGINT, signal.SIGTERM):
            previous[number] = signal.signal(number, lambda *_: stop.set())
    return previous


def serve(
    config,
    out_dir,
    *,
    host="127.0.0.1",
    port=8765,
    device="cpu",
    token_env="HETEROES_TOKEN",
    timeout_seconds=1800,
    worker_ids=None,
    audit_rate=0.05,
    linger_seconds=2,
    initial_adapter=None,
):
    from heteroes.coordinator import Coordinator
    from heteroes.ledger import Ledger
    from heteroes.model.loading import check_recipe_selftest
    from heteroes.runtime_info import JsonlLog
    from heteroes.v3.local import prepare
    from heteroes.v3.run import make_scorer

    secret = _token(token_env)
    if sys.platform == "win32" and (config.get("weightSpace") or {}).get("kind") == "lora" and initial_adapter is None:
        raise ValueError("A Windows coordinator requires --initial-adapter with the pinned LoRA file")
    out = Path(out_dir)
    if out.exists():
        raise FileExistsError("Choose a fresh run directory")
    out.mkdir(parents=True, exist_ok=False)
    ready = prepare(config, out, device, initial_adapter=initial_adapter)
    run = ready["run"]
    check_recipe_selftest(run, device)
    inputs = {"formatVersion": 1, "recipe": run.recipe, "plan": run.plan, "dataset": ready["dataset"]}
    validate_inputs(inputs)
    (out / "inputs.json").write_text(json.dumps(inputs) + "\n", encoding="utf-8")
    published = out / "published"
    published.mkdir(exist_ok=True)
    pinned = []
    if run.recipe["weightSpace"]["kind"] == "lora":
        adapter_hash = run.recipe["weightSpace"]["initialAdapterSha256"]
        shutil.copyfile(out / "initial-adapter.bin", published / (adapter_hash + ".bin"))
        pinned.append(adapter_hash)
    stop = threading.Event()
    handlers = _signals(stop)
    ledger, log, coordinator = None, None, None
    try:
        log = JsonlLog(out / "events.jsonl")
        ledger = Ledger(out / "ledger.sqlite", enforce_chain=True)
        coordinator = Coordinator(
            ready["model"],
            ready["schema"],
            run,
            ledger,
            published,
            experiment_id="local",
            seed_namespace=config.get("candidateSeedNamespace"),
            candidates=run.plan["population"],
            alpha=run.plan["alpha"],
            host=host,
            port=port,
            token=secret,
            log=log,
            dataset=ready["dataset"],
            antithetic=run.antithetic,
            coefficient_rule=run.coefficient_rule,
            coefficient_function=ready["coefficient_function"],
            pinned_weights=pinned,
            score=make_scorer(run, ready["dataset"], ready["python_scorer"]),
            audit_workers=worker_ids,
            audit_rate=audit_rate,
            poll_seconds=0.05,
            timeout_seconds=timeout_seconds,
            cancel_requested=stop.is_set,
            usage_path=out / "usage.sqlite",
        )
        coordinator.server.inputs = inputs
        coordinator.start()
        public = {
            "url": coordinator.url,
            "recipeHash": run.hash,
            "planHash": run.plan_hash,
            "inputsHash": canonical_json_hash(inputs),
        }
        write_json(out / "server.json", public)
        print(json.dumps(public), flush=True)
        summaries = coordinator.run(run.plan["generations"])
        (out / "summaries.json").write_text(json.dumps(summaries, indent=1) + "\n", encoding="utf-8")
        # Leave the terminal FINISHED job visible briefly so external processes can exit cleanly.
        stop.wait(linger_seconds)
        return summaries
    finally:
        if coordinator is not None:
            coordinator.stop()
        if ledger is not None:
            ledger.close()
        if log is not None:
            log.close()
        for number, previous in handlers.items():
            signal.signal(number, previous)


def worker(
    coordinator_url,
    model_path,
    out_dir,
    worker_id,
    *,
    device="cpu",
    token_env="HETEROES_TOKEN",
    expected_recipe_hash=None,
    startup_timeout=600,
):
    from heteroes.executor import CandidateExecutor
    from heteroes.http_transport import HttpClient, TransportError, UnauthorizedError
    from heteroes.manifest import generation_config_sha256
    from heteroes.model.loading import check_recipe_selftest
    from heteroes.replay import ReplayPolicy
    from heteroes.runtime_info import JsonlLog
    from heteroes.v3.model import load, trainable_schema
    from heteroes.worker_runtime import WorkerRuntime, download_weights

    secret = _token(token_env)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=False, mode=0o700)
    cache = out / "cache"
    cache.mkdir()
    client = HttpClient(coordinator_url, token=secret)
    stop = threading.Event()
    handlers = _signals(stop)
    log = JsonlLog(out / "events.jsonl")
    try:
        deadline = time.monotonic() + startup_timeout
        while True:
            try:
                reply = client.get_json("/v1/inputs")
                if reply.get("ok") is not True or "inputs" not in reply:
                    raise ValueError("The coordinator does not expose pinned v3 inputs")
                inputs = reply["inputs"]
                break
            except UnauthorizedError:
                raise
            except TransportError:
                if stop.is_set() or time.monotonic() >= deadline:
                    raise
                stop.wait(0.2)
        run = validate_inputs(inputs, expected_recipe_hash)
        dataset = inputs["dataset"]
        model, tokenizer = load(model_path, run.recipe["model"]["files"], device)
        if (
            generation_config_sha256(model.generation_config.to_dict())
            != run.recipe["evaluation"]["generationConfigSha256"]
        ):
            raise ValueError("Generation configuration differs from the pinned recipe")
        adapter = None
        if run.recipe["weightSpace"]["kind"] == "lora":
            adapter = download_weights(client, run.recipe["weightSpace"]["initialAdapterSha256"], cache)
        schema = trainable_schema(model, run.recipe["weightSpace"], adapter)
        if schema.hash != run.recipe["schemaHash"]:
            raise ValueError("Model schema differs from the pinned recipe")
        check_recipe_selftest(run, device)
        executor = CandidateExecutor(
            model, tokenizer, schema, run, dataset=dataset, chunk=run.chunk, return_completions=True
        )
        (out / "identity.json").write_text(
            json.dumps({"recipeHash": run.hash, "planHash": run.plan_hash, "inputsHash": canonical_json_hash(inputs)})
            + "\n"
        )
        runtime = WorkerRuntime(
            worker_id,
            client,
            executor,
            cache,
            log=log,
            poll_seconds=0.05,
            max_unreachable_seconds=30,
            replay=ReplayPolicy(mode="always", max_chain=64),
        )
        reason = runtime.run(stop)
        return 0 if reason in ("finished", "cancelled", "stopped") else 1
    finally:
        log.close()
        for number, previous in handlers.items():
            signal.signal(number, previous)
