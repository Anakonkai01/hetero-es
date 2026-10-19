#!/usr/bin/env python3
"""Opt-in GPU evidence: v1 pause/restart equality, v2 batches, private HTTP replay/export."""

import argparse
import gc
import json
import os
from pathlib import Path
import secrets
import threading
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-path", type=Path, required=True)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--large", type=Path, required=True)
    parser.add_argument("--storage-volume-uuid", required=True)
    parser.add_argument("--gpu", action="store_true")
    parser.add_argument(
        "--resume-evidence", action="store_true", help="Complete a partial export without repeating completed training"
    )
    args = parser.parse_args()
    if not args.gpu or os.environ.get("HETEROES_GPU_ACCEPTANCE") != "1":
        parser.error("GPU acceptance requires both explicit opt-ins")
    from heteroes.product.storage import checked_directory

    checked_directory(args.large.parent, args.storage_volume_uuid)
    if (args.state / "acceptance.json").exists():
        raise FileExistsError("Completed evidence is immutable")
    args.large.mkdir(mode=0o700, exist_ok=args.resume_evidence)
    args.state.mkdir(mode=0o700, parents=True, exist_ok=args.resume_evidence)
    import torch
    from heteroes.coordinator import Coordinator, RunPaused
    from heteroes.ledger import Ledger
    from heteroes.model.loading import load_pinned_model, build_recipe
    from heteroes.executor import CandidateExecutor
    from heteroes.http_transport import HttpClient
    from heteroes.worker_runtime import WorkerRuntime
    from heteroes.replay import ReplayPolicy
    from heteroes.study.models import inspect
    from heteroes.study.data import dataset
    from heteroes.study.recipe import build
    from heteroes.product.files import write_json

    started = time.time()
    events = []
    worker_errors = []

    def pair(phase, *, resume=False, pause=False, v2=False):
        root = args.state / phase
        root.mkdir(mode=0o700, exist_ok=resume)
        large = args.large / phase
        large.mkdir(mode=0o700, exist_ok=resume)
        write_json(root / "large-data.json", {"directory": str(large), "volumeUUID": args.storage_volume_uuid})
        co_loaded = load_pinned_model(args.model_path, "cuda")
        worker_loaded = load_pinned_model(args.model_path, "cuda")
        data = None
        tracker = None
        if v2:
            manifest = inspect(args.model_path, "Qwen/Qwen2.5-0.5B-Instruct", co_loaded.revision)
            data = dataset(
                {
                    "all": {
                        "format": "json",
                        "content": json.dumps(
                            [{"prompt": f"What is {i} + 7?", "answer": i + 7} for i in range(20, 40)]
                        ),
                    }
                }
            )
            recipe = build(
                co_loaded,
                manifest,
                data,
                sigma=0.001,
                minimum=0.00025,
                generations=2,
                schedule="cosine",
                batch_size=2,
                batch_seed=11,
                max_tokens=32,
            )
            write_json(root / "dataset.json", data)
            write_json(root / "recipe.json", recipe.to_dict())
        else:
            recipe = build_recipe(co_loaded, sigma=0.001, eval_dtype="float32")
        ledger = Ledger(root / "ledger.sqlite", enforce_chain=True)
        pause_after = []

        def completed(summary):
            pause_after.append(summary)
            if tracker is not None:
                tracker.observe(summary["generation"], summary["child_sha256"])

        token = secrets.token_urlsafe(32)
        coordinator = Coordinator(
            co_loaded.model,
            co_loaded.schema,
            recipe,
            ledger,
            large / "weights",
            "gpu-proof-v2" if v2 else "gpu-proof-v1",
            2,
            0.001,
            host="127.0.0.1",
            lease_seconds=60,
            timeout_seconds=600,
            stall_seconds=180,
            device_tokens={"local-proof": token},
            pause_requested=lambda: pause and bool(pause_after),
            generation_completed=completed,
            dataset=data,
            log=lambda event: events.append({"phase": phase, **event}),
        )
        if v2:
            from heteroes.study.tracker import Tracker
            from heteroes.model.weights_io import publish_weights

            tracker = Tracker(root, co_loaded, recipe, data)
            if tracker.best is None:
                tracker.observe(-1, publish_weights(co_loaded.model, co_loaded.schema, large / "weights"))
        client = HttpClient(coordinator.url, token=token, bulk_url=coordinator.url)
        executor = CandidateExecutor(
            worker_loaded.model, worker_loaded.tokenizer, worker_loaded.schema, recipe, dataset=data
        )
        runtime = WorkerRuntime(
            "local-proof",
            client,
            executor,
            large / "cache",
            replay=ReplayPolicy(mode="always", verify_every=1),
            max_unreachable_seconds=20,
            log=lambda event: events.append({"phase": phase, **event}),
        )

        def work():
            try:
                runtime.run()
            except BaseException as error:
                worker_errors.append(f"{type(error).__name__}: {error}")

        coordinator.start()
        thread = threading.Thread(target=work)
        thread.start()
        paused = False
        try:
            try:
                coordinator.run(2)
            except RunPaused:
                paused = True
            thread.join(30)
            if thread.is_alive() or worker_errors:
                raise RuntimeError("Worker did not restore and stop cleanly: " + str(worker_errors))
            generations = ledger.list_generations(coordinator.experiment_id)
            rewards = [
                list(ledger.get_generation_results(coordinator.experiment_id, g.generation).rewards)
                for g in generations
            ]
            records = [ledger.get_update(coordinator.experiment_id, g.generation).record_hash for g in generations]
            result = {
                "paused": paused,
                "finalWeightsSha256": coordinator.parent_sha256,
                "recipeHash": recipe.hash,
                "rewards": rewards,
                "updateHashes": records,
            }
            if v2:
                receipt = tracker.export(samples=32)
                result.update(
                    independentReloadPassed=receipt["independentReloadPassed"],
                    testAccuracy=receipt["test"]["accuracy"],
                    sampledProtocol={"M": 32, "temperature": 0.6, "K": [1, 16, 32]},
                )
            write_json(root / "receipt.json", result)
            return result
        finally:
            coordinator.finish(aborted=bool(worker_errors))
            coordinator.stop()
            thread.join(10)
            ledger.close()

    def clean():
        gc.collect()
        torch.cuda.empty_cache()

    if args.resume_evidence:
        baseline = json.loads((args.state / "baseline/receipt.json").read_text())
        resumed = json.loads((args.state / "paused/receipt.json").read_text())
        paused = {"paused": True, "recoveredFromPartialAcceptance": True}
    else:
        baseline = pair("baseline")
        clean()
        print("Baseline completed", flush=True)
        paused = pair("paused", pause=True)
        clean()
        assert paused["paused"]
        print("Paused at published boundary", flush=True)
        write_json(args.state / "pause-boundary.json", paused)
        resumed = pair("paused", resume=True)
        clean()
    assert resumed["finalWeightsSha256"] == baseline["finalWeightsSha256"]
    assert resumed["rewards"] == baseline["rewards"] and resumed["updateHashes"] == baseline["updateHashes"]
    print("GPU resumed weights/rewards/update records match uninterrupted baseline", flush=True)
    study = pair("study", v2=True, resume=args.resume_evidence)
    clean()
    frozen = [e for e in events if e.get("event") == "generation_inputs_frozen"]
    if not frozen and args.resume_evidence:
        import sqlite3

        with sqlite3.connect((args.state / "study/ledger.sqlite").as_uri() + "?mode=ro", uri=True) as db:
            frozen = [json.loads(r[0]) for r in db.execute("SELECT body FROM generation_context ORDER BY generation")]
    assert (
        len(frozen) == 2
        and frozen[0]["sigmaFloat32"] != frozen[1]["sigmaFloat32"]
        and frozen[0]["batchHash"] != frozen[1]["batchHash"]
    )
    replay = [e for e in events if e.get("event") == "replay"]
    result = {
        "formatVersion": 1,
        "gpuWork": True,
        "hardware": torch.cuda.get_device_name(0),
        "baseline": baseline,
        "paused": paused,
        "resumed": resumed,
        "study": study,
        "pauseResumeEqual": True,
        "frozenContexts": frozen,
        "replayEvents": replay,
        "wallSeconds": time.time() - started,
        "conservativeGpuHours": 2 * (time.time() - started) / 3600,
        "multiGpuAcceptance": False,
        "packagedDesktopAcceptance": False,
        "learningGainClaimed": False,
    }
    result["completedTrainingReused"] = args.resume_evidence
    result["gpuUsageCoversThisInvocationOnly"] = True
    write_json(args.state / "acceptance.json", result)
    write_json(args.state / "events.json", events)
    print(
        "PASS local GPU numerical pause/resume and Recipe v2 export/reload. Evidence:",
        args.state / "acceptance.json",
        flush=True,
    )


if __name__ == "__main__":
    main()
