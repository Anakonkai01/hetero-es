"""Trusted, process-isolated model qualification. Input paths are private agent files, never researcher programs."""

import argparse
import os
from pathlib import Path
from types import SimpleNamespace

from .files import read_json, write_json


class Cancelled(Exception):
    pass


def run(input_path, device):
    root = Path(input_path).parent

    def emit(event):
        if (root / "stop.flag").exists():
            raise Cancelled()
        write_json(
            root / "progress.json",
            {"status": "RUNNING" if event.get("stage") in ("recipe_v3", "chunk_memory") else "PREPARING"},
        )

    try:
        emit({"stage": "start"})
        body = read_json(input_path)
        command = body["command"]
        from heteroes.study.models import validate
        from heteroes.study.prepare import prepare_model
        from .model_qualification import build_reference, check_reference, qualify
        from .agent import request

        validate(command["manifest"], allow_any=True)
        if command["mode"] not in ("BUILD_REFERENCE", "COMPARE_REFERENCE") or command["source"] not in (
            "REFERENCE",
            "UPLOAD",
        ):
            raise ValueError("Invalid fixed probe")
        if command["mode"] == "COMPARE_REFERENCE":
            check_reference(command["reference"], command["manifest"])
        elif command["reference"] is not None:
            raise ValueError("First probe cannot execute a submitted reference")
        config = body["config"]
        config["deviceToken"] = os.environ.pop("HETEROES_TOKEN", "")
        agent = SimpleNamespace(config=config, root=Path(body["stateDirectory"]))

        def call(path, value):
            emit({"stage": "transfer"})
            return request(config["serverUrl"], path, config["deviceToken"], value)

        agent.call = call
        model = prepare_model(
            agent,
            command,
            {"recipeVersion": 3, "modelManifest": command["manifest"], "modelSource": command["source"]},
            emit=emit,
        )
        emit({"stage": "recipe_v3"})
        if command["mode"] == "BUILD_REFERENCE":
            from heteroes.noise.contracts import ENGINE_VERSION

            reference, observations = build_reference(
                model,
                command["manifest"],
                device,
                emit,
                engine=command.get("noiseEngineVersion", ENGINE_VERSION),
                decoder=command.get("decoder", "hf_generate"),
            )
        else:
            reference = None
            observations = qualify(model, command["manifest"], command["reference"], device, emit)
        result = {"status": "COMPLETED", "reference": reference, "observations": observations}
        if device == "cuda":
            # memory and time per chunk on this GPU for this model (suggestions of batch and chunks); never fatal
            emit({"stage": "chunk_memory"})
            try:
                from .chunk_memory import measure

                result["chunkMemory"] = measure(model, command["manifest"]["files"], device)
            except Exception:  # noqa: BLE001 - the qualification itself passed; only the suggestion is missing
                result["chunkMemory"] = None
        emit({"stage": "done"})
    except Cancelled:
        result = {"status": "CANCELLED"}
    except Exception as error:
        # Foreign exception strings may contain transfer grants. Only a stable code leaves this process.
        from heteroes.worker import CandidateFailed
        from heteroes.ledger import FailureKind

        result = {
            "status": "FAILED",
            "errorCode": "RESTORE_MISMATCH"
            if isinstance(error, CandidateFailed) and error.kind is FailureKind.RESTORE_MISMATCH
            else "MODEL_PROBE_FAILED",
        }
    write_json(root / "result.json", result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--device", choices=("cuda", "cpu"), default="cuda")
    parser.add_argument("--gpu", action="store_true")
    args = parser.parse_args()
    if args.device == "cuda" and not args.gpu:
        parser.error("GPU qualification requires --gpu")
    result = run(args.input, args.device)
    return 1 if result["status"] == "FAILED" else 0


if __name__ == "__main__":
    raise SystemExit(main())
