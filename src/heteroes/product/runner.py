"""Managed coordinator subprocess. Control files contain no browser-supplied paths."""
import json
import os
from pathlib import Path
import signal
import sys
import time

from .files import read_json, write_json


def main(directory):
    from heteroes.coordinator import Coordinator, RunCancelled, _NoGeneration
    from heteroes.dispatch import AdmittedOnly, Greedy
    from heteroes.ledger import Ledger
    from heteroes.model.loading import build_recipe, check_noise_selftest, check_recipe_selftest, load_pinned_model
    from heteroes.runtime_info import JsonlLog, code_info, environment_info

    root = Path(directory)
    config = read_json(root / "config.json")
    log = JsonlLog(root / "events.jsonl", append=True)
    def emit(event):
        log({"t": time.time(), **event})
    def state(status, **fields):
        write_json(root / "runner.json", {"status": status, "t": time.time(), **fields})
    def cancel():
        return (root / "cancel.flag").exists()
    def interrupt(*_):
        (root / "cancel.flag").touch()
    signal.signal(signal.SIGTERM, interrupt)
    signal.signal(signal.SIGINT, interrupt)
    coordinator = ledger = None
    policy = config.get("backupPolicy")
    last_summary = None
    outcome = "FAILED"
    failure = None
    try:
        state("STARTING")
        check_noise_selftest()
        loaded = load_pinned_model(config["modelPath"], "cuda")
        recipe = build_recipe(loaded, sigma=config["sigma"], eval_dtype="float32", noise_engine="cpu",
                              workload=config["workload"], decode_engine=config["decodeEngine"])
        check_recipe_selftest(recipe, "cuda")
        ledger = Ledger(root / "ledger.sqlite", max_attempts=3, enforce_chain=True)
        policy=config.get('backupPolicy')
        last_summary=None
        active_policy=policy
        def generation_started(generation):
            nonlocal active_policy
            active_policy=read_json(root/'backup-policy.json',policy)
            write_json(root/f'generation-policy-{generation}.json',active_policy)
            emit({'event':'backup_policy_applied','generation':generation,'policy':active_policy})

        def recovery_point(summary, final=False):
            nonlocal last_summary
            last_summary=summary
            if policy is None:
                return
            try:
                from .recovery import capture_point
                generation_policy=read_json(root/f'generation-policy-{summary["generation"]}.json',active_policy)
                point=capture_point(root,summary,recipe.to_dict(),generation_policy,final=final,
                                    identity={'code':code_info(),'environment':environment_info('cuda')})
                if point:
                    emit({'event':'recovery_point_created','generation':summary['generation'],'pointId':point.name,'final':final})
            except Exception as error:
                # Storage failure never turns a valid numerical update into failure.
                emit({'event':'recovery_point_error','generation':summary['generation'],'errorType':type(error).__name__})
        coordinator = Coordinator(loaded.model, loaded.schema, recipe, ledger, root / "weights", config["runId"],
            config["candidatesPerGeneration"], config["alpha"],
            policy_factory=lambda: AdmittedOnly(Greedy(), config["workerIds"]), host=config["host"], port=config["port"],
            token=os.environ["HETEROES_TOKEN"], timeout_seconds=1800, stall_seconds=300,
            failed_grace_seconds=60, lease_seconds=60, log=emit, cancel_requested=cancel,
            device_tokens=read_json(root/'device-grants.json') if config.get('deviceCredentials') else None,
            generation_completed=recovery_point if policy else None,
            generation_started=generation_started if policy else None)
        coordinator.start()
        next_generation = coordinator.recover()  # finish any recorded update even when cancellation is pending
        if policy and next_generation>0:
            previous=ledger.get_update(config['runId'],next_generation-1)
            parent=next(g.parent_weights_sha256 for g in ledger.list_generations(config['runId']) if g.generation==next_generation-1)
            if previous and previous.applied_at:
                last_summary={'generation':next_generation-1,'child_sha256':previous.child_weights_sha256,'parent_sha256':parent}
        coordinator.server.set_generation(_NoGeneration(), coordinator._job(next_generation, Greedy(), "PREPARING"))
        emit({"event": "managed_start", "recipe": recipe.to_dict(), "recipe_hash": recipe.hash,
              "code": code_info(), "environment": environment_info("cuda")})
        state("PREPARING", recipeHash=recipe.hash)
        deadline = time.monotonic() + 600
        while not (root / "start.flag").exists():
            if cancel():
                raise RunCancelled("cancelled during preparation")
            if time.monotonic() > deadline:
                raise TimeoutError("worker preparation timed out")
            time.sleep(.25)
        state("RUNNING", recipeHash=recipe.hash)
        coordinator.run(config["maxGenerations"])
        outcome = "COMPLETED"
    except RunCancelled:
        outcome = "CANCELLED"
        if coordinator:
            coordinator.finish(cancelled=True)
    except Exception as error:
        failure = f"{type(error).__name__}: {error}"
        emit({"event": "managed_error", "error": failure})
        if coordinator:
            coordinator.finish(aborted=True)
    finally:
        if coordinator and policy and last_summary is not None:
            recovery_point(last_summary,final=True)
        summary = {"status": outcome, "failureReason": failure,
                   "final_weights_sha256": coordinator.parent_sha256 if coordinator else None}
        write_json(root / f"summary-{time.time_ns()}.json", summary)
        state(outcome, **{key: value for key, value in summary.items() if key != "status"})
        if coordinator:
            deadline = time.monotonic() + 600
            while not (root / "workers-stopped.flag").exists() and time.monotonic() < deadline:
                time.sleep(.25)
            coordinator.stop()
        if ledger:
            ledger.close()
        log.close()
    return 0 if outcome in ("COMPLETED", "CANCELLED") else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
