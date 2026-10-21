"""The live lab as a notebook sees it: one signed-in session, experiments, device switches and polled frames.

The session comes from `scripts/lab-login.py` (~/.config/heteroes-demo/session.json, 0600); no secret is ever written by
this module or printed into a notebook.
"""

import json
import os
from pathlib import Path
import time

from heteroes.demo.state import build_frame
from heteroes.v3.lab_cli import Lab, offer_experiment

SESSION = Path.home() / ".config" / "heteroes-demo" / "session.json"
TOKEN_ENV = "HETEROES_DEMO_ACCESS_TOKEN"
TERMINAL = ("COMPLETED", "FAILED", "CANCELLED")


class DemoLab:
    def __init__(self, session=SESSION, api=None):
        if api is None:
            value = json.loads(Path(session).read_text())
            os.environ[TOKEN_ENV] = value["token"]
            api = Lab(value["url"], value["workspace"], TOKEN_ENV)
        self.api = api

    def request(self, method, path, body=None):
        return self.api.request(method, path, body)

    def devices(self):
        return self.request("GET", "/api/v1/devices")

    def device(self, worker_id):
        found = [d for d in self.devices() if d["workerId"] == worker_id]
        if not found:
            raise LookupError(f"No device of this account runs worker {worker_id}")
        return found[0]

    def set_contribution(self, worker_id, enabled):
        """The owner's ON/OFF switch for this boot; OFF makes a member of a running experiment leave it (ADR-009)."""
        d = self.device(worker_id)
        return self.request(
            "POST", f"/api/v1/devices/{d['deviceId']}/contribution", {"enabled": enabled, "bootId": d["bootId"]}
        )

    def offer(self, spec, coordinator_device_id, worker_ids, directory):
        """Upload the pinned model/data once (idempotent per directory), create the experiment and submit it."""
        experiment = offer_experiment(spec, coordinator_device_id, worker_ids, self.api, directory)
        if experiment["status"] == "DRAFT":
            experiment = self.request("POST", f"/api/v1/experiments/{experiment['experimentId']}/submit")
        return experiment

    def experiment(self, run_id):
        return self.request("GET", f"/api/v1/experiments/{run_id}")

    def timeline(self, run_id):
        return self.request("GET", f"/api/v1/experiments/{run_id}/timeline")

    def events(self, run_id):
        """This run's events of the lab feed (the newest 2,000 of all runs: enough while a run is watched)."""
        return [e for e in self.request("GET", "/api/v1/events") if e.get("experimentId") == run_id]

    def frame(self, run_id, names=None):
        timeline = self.timeline(run_id)
        return build_frame(timeline, self.events(run_id), names), timeline

    def follow(self, run_id, names=None, every=3.0, until=None, sleep=time.sleep):
        """Yield (frame, timeline) every `every` seconds until the run ends or `until(frame)` is true."""
        while True:
            frame, timeline = self.frame(run_id, names)
            yield frame, timeline
            if frame.status in TERMINAL or (until is not None and until(frame)):
                return
            sleep(every)


def wait_until(check, timeout, every=5.0, clock=time.monotonic, sleep=time.sleep):
    """Call `check()` until it returns something true; that value, or TimeoutError after `timeout` seconds."""
    deadline = clock() + timeout
    while True:
        value = check()
        if value:
            return value
        if clock() >= deadline:
            raise TimeoutError(f"condition not met within {timeout} s")
        sleep(every)
