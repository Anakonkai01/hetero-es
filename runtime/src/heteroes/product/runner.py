"""Managed coordinator subprocess. Control files contain no browser-supplied paths."""

import json
import math
import os
from pathlib import Path
import signal
import sys
import time

from .files import read_json, write_json
from .storage import data_root


def apply_backup_policy(root, generation, current, emit):
    """Optional policy persistence cannot stop otherwise valid computation."""

    def log(event):
        try:
            emit(event)
        except Exception:
            pass

    try:
        policy = read_json(root / "backup-policy.json", current)
        if (
            not isinstance(policy, dict)
            or set(policy) != {"interval", "retain"}
            or any(type(v) is not int or not 1 <= v <= 1000 for v in policy.values())
        ):
            raise ValueError("Invalid operational backup policy")
    except Exception as error:
        log({"event": "backup_policy_error", "generation": generation, "errorType": type(error).__name__})
        return current
    try:
        write_json(root / f"generation-policy-{generation}.json", policy)
    except Exception as error:
        log({"event": "backup_policy_error", "generation": generation, "errorType": type(error).__name__})
    log({"event": "backup_policy_applied", "generation": generation, "policy": policy})
    return policy


class _Background:
    """Run one function on a thread; `join` waits and raises what it raised."""

    def __init__(self, function):
        import threading

        self.error = None
        self.thread = threading.Thread(target=self._run, args=(function,), daemon=True)
        self.thread.start()

    def _run(self, function):
        try:
            function()
        except BaseException as error:  # handed to the main thread by join
            self.error = error

    def join(self):
        self.thread.join()
        if self.error is not None:
            raise self.error


def pause_check(root, reserve_bytes, emit, usage=None):
    """The coordinator's pause request: the lab's pause, or less free disk than `reserve_bytes` where the run writes.

    Overnight 2026-10-23: a soak run failed at generation 60 with "No space left on device". Pausing at the generation
    boundary instead keeps a verified checkpoint (hard links, a few MB), so the run resumes once space is freed.
    """
    import shutil

    usage = usage or shutil.disk_usage
    said = []

    def check():
        if (root / "pause.flag").exists():
            return True
        free = usage(data_root(root)).free
        if free >= reserve_bytes:
            return False
        if not said:
            said.append(True)
            emit({"event": "paused_low_disk", "freeBytes": free, "reserveBytes": reserve_bytes})
        return True

    return check


def scheduling(config, ledger, members=None):
    """The coordinator's policy factory: only the members get work (`members` returns the current ones, elastic membership;
    default: the selected workers), and one speed book serves the whole run, seeded from what the ledger already knows
    after a restart (ADR-009)."""
    from heteroes.dispatch import SpeedBook, policy_factory

    return policy_factory(
        config.get("schedulerPolicy", "greedy"),
        config["workerIds"] if members is None else members,
        book=SpeedBook.from_ledger(ledger, config["runId"]),
    )


def derived_limit(book, workers, candidates, *, floor, factor):
    """Seconds a generation (or one audit) may take: `factor` times the work of the slowest member, never less than the old fixed
    `floor` (ADR-009). `workers` is a list or a function returning the current members."""
    members = workers() if callable(workers) else workers
    known = [book.estimate(w) for w in members if book.estimate(w) is not None]
    if not known:
        return floor
    return max(floor, factor * math.ceil(candidates / len(members)) * max(known))


def generation_limit(derived, hard_cap=None):
    """D11: the measured-speed limit, never above the researcher's/operator's explicit hard cap."""
    return derived if hard_cap is None else min(derived, float(hard_cap))


def main(directory, *, device="cuda", timeout_seconds=1800):
    from heteroes.coordinator import Coordinator, RunCancelled, RunPaused, _NoGeneration
    from heteroes.dispatch import Greedy
    from heteroes.ledger import Ledger
    from heteroes.model.loading import build_recipe, check_noise_selftest, check_recipe_selftest, load_pinned_model
    from heteroes.runtime_info import JsonlLog, code_info, environment_info

    root = Path(directory)
    config = read_json(root / "config.json")
    if config.get("recipeVersion") == 3:
        from heteroes.v3.audit import freeze_audit_config

        freeze_audit_config(root, config.get("auditRate", 0.05))
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
    paused_checkpoint = None
    tracker = None
    base_validation = None
    try:
        state("STARTING")
        check_noise_selftest()
        dataset = None
        if config.get("recipeVersion") == 3:
            from heteroes.product.v3 import prepare_run

            loaded, recipe, dataset = prepare_run(config, root, device)
        elif config.get("recipeVersion") == 2:
            from heteroes.study.models import load
            from heteroes.study.data import verify
            from heteroes.study.recipe import build

            loaded = load(config["modelPath"], config["modelManifest"], device)
            dataset = verify(read_json(Path(config["datasetPath"])))
            recipe = build(
                loaded,
                config["modelManifest"],
                dataset,
                sigma=config["sigma"],
                minimum=config["sigmaMinimum"],
                generations=config["maxGenerations"],
                schedule=config["sigmaSchedule"],
                batch_size=config["batchSize"],
                batch_seed=config["batchSeed"],
                max_tokens=config["maxNewTokens"],
            )
        else:
            loaded = load_pinned_model(config["modelPath"], device)
            recipe = build_recipe(
                loaded,
                sigma=config["sigma"],
                eval_dtype="float32",
                noise_engine="cpu",
                workload=config["workload"],
                decode_engine=config["decodeEngine"],
            )
        check_recipe_selftest(recipe, device)
        ledger = Ledger(root / "ledger.sqlite", max_attempts=3, enforce_chain=True)
        policy = config.get("backupPolicy")
        last_summary = None
        active_policy = policy

        from .membership import Membership

        grants = read_json(root / "device-grants.json") if config.get("deviceCredentials") else None
        membership = Membership(ledger, config["runId"], config["workerIds"], root, emit, grants=grants)

        def generation_started(generation):
            nonlocal active_policy
            data_root(root)  # Check the selected volume before opening work.
            membership.apply(generation, coordinator)  # joins and leaves take effect here, at the boundary (ADR-009)
            if policy:
                active_policy = apply_backup_policy(root, generation, active_policy, emit)

        def recovery_point(summary, final=False):
            nonlocal last_summary
            last_summary = summary
            if tracker is not None and not final:
                tracker.observe(summary["generation"], summary["child_sha256"])
            if policy is None:
                return
            try:
                from .recovery import capture_point, source_identity

                generation_policy = read_json(root / f"generation-policy-{summary['generation']}.json")
                if generation_policy is None:
                    generation_policy = read_json(root / "backup-policy.json", active_policy)
                point = capture_point(
                    root,
                    summary,
                    recipe.to_dict(),
                    generation_policy,
                    final=final,
                    identity={
                        "code": {**code_info(), **source_identity(Path(__file__).resolve().parents[1])},
                        "environment": environment_info(device),
                    },
                )
                if point:
                    emit(
                        {
                            "event": "recovery_point_created",
                            "generation": summary["generation"],
                            "pointId": point.name,
                            "final": final,
                        }
                    )
            except Exception as error:
                # Storage failure never turns a valid numerical update into failure.
                emit(
                    {
                        "event": "recovery_point_error",
                        "generation": summary["generation"],
                        "errorType": type(error).__name__,
                    }
                )

        v3_options = {}
        if config.get("recipeVersion") == 3:
            from heteroes.product.v3 import python_functions
            from heteroes.v3.run import make_scorer

            # researcher code (web lab, owner 2026-10-20) runs here only, in child processes with a time limit
            python_scorer, coefficient_function, recipe.sampler_function = python_functions(config, root)
            v3_options = {
                "seed_namespace": config.get("candidateSeedNamespace"),
                "audit_workers": config["workerIds"],
                "audit_rate": config.get("auditRate", 0.05),
                "audit_fault_path": root / "audit-faults.json",
                "antithetic": recipe.antithetic,
                "coefficient_rule": recipe.coefficient_rule,
                "score": make_scorer(recipe, dataset, python_scorer),
                "coefficient_function": coefficient_function,
                "pinned_weights": [recipe.recipe["weightSpace"]["initialAdapterSha256"]]
                if recipe.recipe["weightSpace"]["kind"] == "lora"
                else [],
            }
        scheduler = scheduling(config, ledger, membership.current)
        coordinator = Coordinator(
            loaded.model,
            loaded.schema,
            recipe,
            ledger,
            data_root(root) / "weights",
            config["runId"],
            config["candidatesPerGeneration"],
            config["alpha"],
            policy_factory=scheduler,
            host=config["host"],
            port=config["port"],
            token=os.environ["HETEROES_TOKEN"],
            timeout_seconds=lambda _: generation_limit(
                derived_limit(
                    scheduler.book,
                    membership.current,
                    config["candidatesPerGeneration"],
                    floor=timeout_seconds,
                    factor=4,
                ),
                config.get("hardCapSeconds"),
            ),
            audit_timeout_seconds=lambda _: derived_limit(scheduler.book, membership.current, 1, floor=120, factor=3),
            stall_seconds=config.get("stallSeconds", 300),
            generation_clock_path=root / "generation-clock.json",
            restore_recovery_path=root / "restore-recoveries.json" if config.get("recipeVersion") == 3 else None,
            failed_grace_seconds=60,
            lease_seconds=60,
            log=emit,
            cancel_requested=cancel,
            usage_path=root / "usage.sqlite" if config.get("recipeVersion") == 3 else None,
            # until the first boundary the workers that joined before a restart can authenticate too (ADR-009)
            device_tokens=None if grants is None else membership.all_grants(),
            generation_completed=recovery_point if policy or dataset is not None else None,
            generation_started=generation_started,
            # room for the next published weights, an export and a margin (each about the model's size)
            pause_requested=pause_check(
                root, 3 * sum(p.numel() * p.element_size() for p in loaded.model.parameters()) + 2**30, emit
            ),
            dataset=dataset,
            **v3_options,
        )
        coordinator.start()
        next_generation = coordinator.recover()  # finish any recorded update even when cancellation is pending
        if dataset is not None:
            if config.get("recipeVersion") == 3:
                from heteroes.v3.tracker import Tracker

                tracker = Tracker(
                    root,
                    loaded,
                    recipe,
                    dataset,
                    config.get("validationInterval", 1),
                    model_path=config["modelPath"],
                    log=emit,
                    python_scorer=python_scorer,
                )
            else:
                from heteroes.study.tracker import Tracker

                tracker = Tracker(root, loaded, recipe, dataset, config.get("validationInterval", 1))
            if next_generation == 0 and tracker.best is None:
                from heteroes.model.weights_io import publish_weights

                initial = publish_weights(loaded.model, loaded.schema, data_root(root) / "weights")
                base_validation = lambda: tracker.observe(-1, initial)  # noqa: E731
            elif next_generation > 0:
                tracker.observe(next_generation - 1, coordinator.parent_sha256)
        if policy and next_generation > 0:
            previous = ledger.get_update(config["runId"], next_generation - 1)
            parent = next(
                g.parent_weights_sha256
                for g in ledger.list_generations(config["runId"])
                if g.generation == next_generation - 1
            )
            if previous and previous.applied_at:
                last_summary = {
                    "generation": next_generation - 1,
                    "child_sha256": previous.child_weights_sha256,
                    "parent_sha256": parent,
                }
        emit(
            {
                "event": "managed_start",
                "schedulerPolicy": scheduler.policy_name,
                "recipe": recipe.to_dict(),
                "recipe_hash": recipe.hash,
                "code": code_info(),
                "environment": environment_info(device),
            }
        )
        if next_generation < config["maxGenerations"]:
            coordinator.server.set_generation(_NoGeneration(), coordinator._job(next_generation, Greedy(), "PREPARING"))
            state("PREPARING", recipeHash=recipe.hash)
            emit({"event": "preparing", "generation": next_generation})
            # The base model is validated on this GPU while the workers load theirs (about 20 s saved per run,
            # overnight 2026-10-23); the first generation opens only after it is done.
            validating = _Background(base_validation) if base_validation else None
            deadline = time.monotonic() + 600
            try:
                while not (root / "start.flag").exists():
                    if cancel():
                        raise RunCancelled("cancelled during preparation")
                    if time.monotonic() > deadline:
                        raise TimeoutError("worker preparation timed out")
                    time.sleep(0.25)
            finally:
                if validating:
                    validating.join()
        elif base_validation:
            base_validation()
        state("RUNNING", recipeHash=recipe.hash)
        if next_generation < config["maxGenerations"]:
            coordinator.run(config["maxGenerations"])
        else:
            coordinator.finish()
        outcome = "COMPLETED"
    except RunPaused:
        try:
            if not policy or last_summary is None:
                raise ValueError("Pause requires a completed recovery checkpoint")
            from .recovery import capture_point, verify_point, source_identity

            point = capture_point(
                root,
                last_summary,
                recipe.to_dict(),
                active_policy,
                final=True,
                identity={
                    "code": {**code_info(), **source_identity(Path(__file__).resolve().parents[1])},
                    "environment": environment_info(device),
                },
            )
            manifest = verify_point(point)
            paused_checkpoint = {
                key: manifest[key] for key in ("pointId", "generation", "childWeightsSha256", "parentWeightsSha256")
            }
            paused_checkpoint["verified"] = True
            write_json(root / "pause-point.json", paused_checkpoint)
            emit({"event": "generation_boundary_pause", **paused_checkpoint})
            outcome = "PAUSED"
        except Exception as error:
            failure = f"Pause checkpoint failed: {type(error).__name__}"
            emit({"event": "pause_checkpoint_error", "errorType": type(error).__name__})
            if coordinator:
                coordinator.finish(aborted=True)
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
        if coordinator and policy and last_summary is not None and outcome != "PAUSED":
            recovery_point(last_summary, final=True)
        summary = {
            "status": outcome,
            "failureReason": failure,
            "final_weights_sha256": coordinator.parent_sha256 if coordinator else None,
        }
        if paused_checkpoint is not None:
            summary["pauseCheckpoint"] = paused_checkpoint
        write_json(root / f"summary-{time.time_ns()}.json", summary)
        state(outcome, **{key: value for key, value in summary.items() if key != "status"})
        if coordinator:
            deadline = time.monotonic() + 600
            while not (root / "workers-stopped.flag").exists() and time.monotonic() < deadline:
                time.sleep(0.25)
            coordinator.stop()
            if tracker is not None and outcome == "COMPLETED" and (root / "workers-stopped.flag").exists():
                try:
                    receipt = tracker.export()
                    emit(
                        {
                            "event": "study_export_verified",
                            "weightsSha256": receipt["weightsSha256"],
                            "testReward" if config.get("recipeVersion") == 3 else "testAccuracy": receipt["test"][
                                "meanReward" if config.get("recipeVersion") == 3 else "accuracy"
                            ],
                        }
                    )
                except Exception as error:
                    write_json(
                        root / "study-export-error.json", {"errorType": type(error).__name__, "exportVerified": False}
                    )
                    emit({"event": "study_export_error", "errorType": type(error).__name__})
        if ledger:
            ledger.close()
        log.close()
    return 0 if outcome in ("COMPLETED", "CANCELLED", "PAUSED") else 1


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory")
    parser.add_argument("--device", choices=("cpu", "cuda"), default="cuda")
    args = parser.parse_args()
    sys.exit(main(args.directory, device=args.device))
