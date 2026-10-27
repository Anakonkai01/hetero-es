"""An agent's durable model-probe ownership. Process identity uncertainty always holds the GPU."""

import re
import sys

from heteroes.canonical import canonical_json_hash
from heteroes.study.models import validate
from .files import read_json, write_json
from .model_qualification import check_reference
from .remote import handle as remote_handle
from .run_supervisor import ROOT, QUIESCENT

TERMINAL = {"COMPLETED", "FAILED", "CANCELLED"}


class ModelProbeManager:
    def __init__(self, agent):
        self.agent = agent
        self.root = agent.root / "model-probes"
        self.root.mkdir(mode=0o700, exist_ok=True)
        self.sent_terminal = set()

    def directory(self, job_id):
        if not isinstance(job_id, str) or re.fullmatch("[a-f0-9]{32}", job_id) is None:
            from .agent import InvalidCommand

            raise InvalidCommand("Invalid model qualification identity")
        return self.root / job_id

    @staticmethod
    def ownership(root):
        from .agent import owned_state

        return owned_state(read_json(root / "process.json"), (root / "launch-intent.json").exists())

    def busy(self):
        return any(self.ownership(root) is not False for root in self.root.iterdir() if root.is_dir())

    def training_busy(self):
        if any(
            self.agent.manager.state(root).get("status") not in QUIESCENT
            for root in self.agent.manager.root.iterdir()
            if root.is_dir() and (root / "assignment.json").exists()
        ):
            return True
        return any(p["coordinatorAlive"] is not False or p["workerAlive"] is not False for p in self.agent.observe())

    def start(self, command):
        root = self.directory(command.get("jobId"))
        frozen = {k: command[k] for k in ("jobId", "mode", "source", "manifest", "reference")}
        # optional: the reference's noise engine and decoder (absent in older commands, whose bytes stay frozen)
        frozen |= {k: command[k] for k in ("noiseEngineVersion", "decoder") if command.get(k) is not None}
        if frozen.get("decoder", "hf_generate") not in ("hf_generate", "strict_b22_v1"):
            raise ValueError("Invalid model probe decoder")
        validate(frozen["manifest"], allow_any=True)
        if frozen["mode"] not in ("BUILD_REFERENCE", "COMPARE_REFERENCE") or frozen["source"] not in (
            "REFERENCE",
            "UPLOAD",
        ):
            raise ValueError("Invalid model probe mode or source")
        if frozen["mode"] == "COMPARE_REFERENCE":
            check_reference(frozen["reference"], frozen["manifest"])
        elif frozen["reference"] is not None:
            raise ValueError("First probe must establish the trusted reference")
        previous = read_json(root / "command.json")
        if previous is not None and canonical_json_hash(previous) != canonical_json_hash(frozen):
            raise ValueError("Frozen model probe changed")
        if (root / "stop.flag").exists():
            if not (root / "launch-intent.json").exists() and not (root / "process.json").exists():
                write_json(root / "result.json", {"status": "CANCELLED"})
            return
        if previous:
            if (
                read_json(root / "process.json")
                or (root / "launch-intent.json").exists()
                or (root / "result.json").exists()
            ):
                return
        if not self.agent.enabled:
            raise RuntimeError("Contribution is OFF for this boot")
        if self.busy() or self.training_busy():
            raise RuntimeError("Wait for confirmed GPU release before a model probe")
        write_json(root / "command.json", frozen)
        config = {
            k: v
            for k, v in self.agent.config.items()
            if k in ("serverUrl", "modelPath", "modelPaths", "largeDataDirectory", "storageVolumeUUID")
        }
        write_json(root / "input.json", {"command": frozen, "config": config, "stateDirectory": str(self.agent.root)})
        remote_handle(
            {
                "action": "start",
                "directory": str(root),
                "source": str(ROOT / "src"),
                "token": self.agent.config["deviceToken"],
                "argv": [
                    sys.executable,
                    "-m",
                    "heteroes.product.model_probe",
                    "--input",
                    str(root / "input.json"),
                    "--gpu",
                ],
            }
        )

    def cancel(self, job_id):
        root = self.directory(job_id)
        root.mkdir(mode=0o700, exist_ok=True)
        (root / "stop.flag").touch(mode=0o600)
        if self.ownership(root) is False and not (root / "result.json").exists():
            write_json(root / "result.json", {"status": "CANCELLED"})

    def cancel_all(self):
        for root in self.root.iterdir():
            if root.is_dir() and not (root / "acknowledged.flag").exists():
                self.cancel(root.name)

    def reports(self):
        reports = []
        self.sent_terminal.clear()
        for root in sorted(self.root.iterdir()):
            if not root.is_dir() or (root / "acknowledged.flag").exists():
                continue
            ownership = self.ownership(root)
            result = read_json(root / "result.json")
            if result is None:
                if ownership is False:
                    result = (
                        {"status": "CANCELLED"}
                        if (root / "stop.flag").exists()
                        else {"status": "FAILED", "errorCode": "MODEL_PROBE_PROCESS_EXITED"}
                    )
                    write_json(root / "result.json", result)
                else:
                    result = read_json(root / "progress.json", {"status": "PREPARING"})
            report = {"jobId": root.name, **result, "processAlive": ownership}
            if ownership is False and report["status"] in TERMINAL:
                self.sent_terminal.add(root.name)
            reports.append(report)
            if len(reports) == 10:
                break
        return reports

    def acknowledge(self, accepted):
        for job_id in accepted:
            if job_id in self.sent_terminal:
                root = self.directory(job_id)
                (root / "acknowledged.flag").touch(mode=0o600)
                # The terminal receipt is public numerical evidence; transient download credentials are not retained.
                (root / "input.json").unlink(missing_ok=True)
