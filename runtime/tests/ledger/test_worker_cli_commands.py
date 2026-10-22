"""The CLI Worker's own commands (plan 2026-10-22, phase 3b): resumable downloads, readable errors and status, the
service, setup from scratch to ON, contribution/rename/forget as the device, update and clean."""

import argparse
import io
import json
import time
import urllib.error

import pytest

from heteroes.product import worker_cli, worker_service
from heteroes.product.worker_cli import LabError, Worker, explain, render_status, setup, verified_download
from test_worker_cli import SELF_TEST, bundle, item


class Body(io.BytesIO):
    def __init__(self, data, status=200):
        super().__init__(data)
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_a_download_cut_by_the_network_is_retried_and_resumes_where_it_stopped(tmp_path, monkeypatch):
    data = bytes(range(256)) * 40
    wanted = {**item(tmp_path, "w.whl", data), "url": "https://downloads.invalid/w.whl"}
    ranges, said = [], []

    def urlopen(request, timeout):
        ranges.append(request.get_header("Range"))
        if len(ranges) == 1:
            partial = tmp_path / "out" / "w.whl.part"
            partial.write_bytes(data[:4000])  # what arrived before the connection broke
            raise urllib.error.URLError(ConnectionResetError())
        start = int(request.get_header("Range")[6:-1])
        return Body(data[start:], status=206)

    monkeypatch.setattr(worker_cli.urllib.request, "urlopen", urlopen)
    target = verified_download(wanted, tmp_path / "out", said.append, sleep=lambda _: None)
    assert target.read_bytes() == data
    assert ranges == [None, "bytes=4000-"]
    assert any("retrying" in line for line in said)


def test_a_download_that_keeps_failing_says_so_and_a_missing_file_is_not_retried(tmp_path, monkeypatch):
    wanted = {**item(tmp_path, "w.whl", b"x"), "url": "https://downloads.invalid/w.whl"}
    calls = []

    def broken(request, timeout):
        calls.append(1)
        raise urllib.error.URLError(TimeoutError())

    monkeypatch.setattr(worker_cli.urllib.request, "urlopen", broken)
    with pytest.raises(RuntimeError, match="DOWNLOAD_FAILED"):
        verified_download(wanted, tmp_path / "out", lambda *_: None, attempts=3, sleep=lambda _: None)
    assert len(calls) == 3

    def missing(request, timeout):
        calls.append(1)
        raise urllib.error.HTTPError(request.full_url, 404, "Not Found", {}, None)

    calls.clear()
    monkeypatch.setattr(worker_cli.urllib.request, "urlopen", missing)
    with pytest.raises(RuntimeError, match="HTTP 404"):
        verified_download(wanted, tmp_path / "out", lambda *_: None, sleep=lambda _: None)
    assert len(calls) == 1


def test_errors_say_what_happened_and_what_to_do_and_keep_the_code():
    text = explain(RuntimeError("PAIRING_REFUSED"))
    assert "refused the pairing code" in text and "10 minutes" in text and "[PAIRING_REFUSED]" in text
    assert "[LAB_HTTP_401]" in explain(LabError(401)) and "forget" in explain(LabError(401))
    assert "busy" in explain(LabError(524))
    assert explain(RuntimeError("DOWNLOAD_FAILED: t.whl (HTTP 404)")).startswith(
        "error: A download kept failing. (t.whl"
    )
    assert explain(RuntimeError("something new")) == "error: something new"


class FakeService:
    def __init__(self, available=True):
        self._available, self.unit, self.calls = available, None, []

    def available(self):
        return self._available

    def installed(self):
        return self.unit is not None

    def install(self, command, home):
        self.unit = (command, home)
        return None

    def active(self):
        return "start" in self.calls or "restart" in self.calls

    def enabled(self):
        return self.unit is not None

    def ensure_linger(self):
        return None

    def __getattr__(self, name):
        if name in ("start", "stop", "restart", "remove"):
            return lambda: self.calls.append(name)
        raise AttributeError(name)


class FakeLab:
    """The routes the CLI uses, as an approved-after-a-while lab sees them."""

    def __init__(self, approve_after=2):
        self.requests, self.approve_after, self.summaries = [], approve_after, 0
        self.state = {"approvalStatus": "PENDING", "contributionDesired": False, "keep": False}

    def __call__(self, url, path, token, body, method=None):
        self.requests.append((path, token, body, method))
        if path == "/api/v1/health":
            return {"agentMode": True, "uiUrl": "https://lab.example", "recipeVersions": [3]}
        if path == "/api/v1/device/enroll":
            return {
                "deviceId": "d" * 32,
                "workerId": body["workerId"],
                "deviceToken": "tok",
                "approvalStatus": "PENDING",
            }
        if path == "/api/v1/device/summary":
            self.summaries += 1
            if self.summaries >= self.approve_after:
                self.state["approvalStatus"] = "APPROVED"
            return {
                "deviceId": "d" * 32,
                "displayName": "box",
                "approvalStatus": self.state["approvalStatus"],
                "contributionDesired": self.state["contributionDesired"],
                "contributionEnabled": self.state["contributionDesired"],
                "keepContributionAfterReboot": self.state["keep"],
                "runs": [],
            }
        if path == "/api/v1/device/contribution":
            if self.state["approvalStatus"] != "APPROVED":
                raise LabError(409)
            self.state["contributionDesired"] = body["enabled"]
            self.state["keep"] = body.get("keepAfterReboot", self.state["keep"])
            return {"enabled": body["enabled"]}
        if path == "/api/v1/device/name":
            return {"displayName": body["displayName"]}
        if path == "/api/v1/device" and method == "DELETE":
            if self.state["contributionDesired"]:
                raise LabError(409)
            return None
        raise AssertionError(path)


def options(**changes):
    return argparse.Namespace(
        **{
            "lab": "https://lab.example",
            "name": "box",
            "coordinator": False,
            "host": None,
            "cpu": False,
            "on": True,
            "keep": True,
            "yes": True,
            "approval_timeout": 60,
            **changes,
        }
    )


def ready(tmp_path, monkeypatch):
    worker = bundle(tmp_path)
    worker.service = FakeService()
    worker.install(run=lambda *a, **k: None)
    worker.save_settings({"selfTest": SELF_TEST})
    monkeypatch.setattr(worker, "doctor", lambda *a, **k: [{"level": "ok", "check": "GPU", "detail": "", "fix": ""}])
    monkeypatch.setattr(worker_cli, "read_code", lambda: "CODE-9")
    monkeypatch.setattr(worker, "agent_online", lambda within=60: True)
    return worker


def test_setup_pairs_starts_the_service_waits_for_approval_and_turns_on(tmp_path, monkeypatch):
    worker, lab = ready(tmp_path, monkeypatch), FakeLab(approve_after=4)
    said = []
    worker.say = said.append

    setup(worker, options(), call=lab, sleep=lambda _: None)

    assert worker.settings()["serverUrl"] == "https://lab.example" and worker.paths()["token"].read_text() == "tok"
    enroll = next(body for path, _, body, _ in lab.requests if path == "/api/v1/device/enroll")
    assert enroll["code"] == "CODE-9" and enroll["displayName"] == "box"
    assert worker.service.unit is not None and "start" in worker.service.calls
    assert lab.state == {"approvalStatus": "APPROVED", "contributionDesired": True, "keep": True}
    assert any("waiting for an administrator" in line for line in said)
    assert "tok" not in " ".join(map(str, said))
    # running it again resumes: nothing is installed, tested or paired twice, and ON is not asked again
    lab.requests.clear()
    setup(worker, options(), call=lab, sleep=lambda _: None)
    assert {p for p, *_ in lab.requests} == {"/api/v1/device/summary"}


def test_setup_without_a_service_tells_how_to_run_by_hand(tmp_path, monkeypatch):
    worker, lab = ready(tmp_path, monkeypatch), FakeLab()
    worker.service = FakeService(available=False)
    said = []
    worker.say = said.append
    setup(worker, options(), call=lab, sleep=lambda _: None)
    assert any("tmux" in line for line in said) and lab.state["contributionDesired"] is False


def test_on_off_rename_and_forget_act_as_the_device(tmp_path, monkeypatch):
    worker, lab = ready(tmp_path, monkeypatch), FakeLab(approve_after=1)
    worker.join("https://lab.example", "C", "box", call=lab)
    with pytest.raises(RuntimeError, match="NOT_READY_FOR_CONTRIBUTION"):
        worker.contribution(True, call=lab)  # still PENDING
    worker.summary(call=lab)
    worker.contribution(True, True, call=lab)
    assert lab.requests[-1][1:] == ("tok", {"enabled": True, "keepAfterReboot": True}, None)
    with pytest.raises(RuntimeError, match="FORGET_BUSY"):
        worker.forget(call=lab)  # still ON: the lab keeps it, and so does this machine
    assert worker.paths()["token"].exists()
    worker.contribution(False, call=lab)
    assert lab.requests[-1][2] == {"enabled": False}
    worker.rename("5070ti-nhut", call=lab)
    assert worker.settings()["device"]["displayName"] == "5070ti-nhut"
    worker.forget(call=lab)
    assert not worker.paths()["token"].exists() and "device" not in worker.settings()
    assert lab.requests[-1][0] == "/api/v1/device" and lab.requests[-1][3] == "DELETE"


def test_status_reads_like_a_sentence(tmp_path, monkeypatch):
    worker, lab = ready(tmp_path, monkeypatch), FakeLab(approve_after=1)
    worker.join("https://lab.example", "C", "box", call=lab)
    worker.summary(call=lab)
    worker.contribution(True, True, call=lab)
    status = worker.status(call=lab)
    status["lab"]["runs"] = [
        {
            "experimentId": "e" * 32,
            "name": "GSM8K tier 3",
            "status": "RUNNING",
            "role": "worker",
            "completedGenerations": 41,
            "maxGenerations": 300,
        }
    ]
    status["gpu"] = {
        "name": "NVIDIA GeForce RTX 5070 Ti",
        "vramUsedMb": 9318,
        "vramTotalMb": 16303,
        "temperatureC": 63,
        "powerDrawW": 210,
        "utilizationPercent": 97,
    }
    text = render_status(status)
    assert text.splitlines()[0] == "box  ·  https://lab.example"
    assert "Contribution  ON (stays ON after restart)" in text
    assert "Run           GSM8K tier 3 (worker, generation 41/300, RUNNING)" in text
    assert "9.1/15.9 GB · 63 °C · 210 W · 97% busy" in text
    assert json.dumps(status)  # --json prints the same data
    assert "Lab contact   none for 33 min" in render_status(
        {**status, "connection": {"status": "ONLINE", "t": time.time() - 1980}}
    )
    bad = {**status, "lab": {"error": "LAB_HTTP_401"}}
    assert "no longer accepts this machine's key" in render_status(bad)


def test_update_waits_while_the_machine_is_in_a_run(tmp_path, monkeypatch):
    worker, lab = ready(tmp_path, monkeypatch), FakeLab(approve_after=1)
    worker.join("https://lab.example", "C", "box", call=lab)
    monkeypatch.setattr(worker, "summary", lambda call=None: {"runs": [{"experimentId": "e" * 32}]})
    with pytest.raises(RuntimeError, match="UPDATE_BUSY"):
        worker_cli.update(worker, argparse.Namespace(force=False), call=lab)


def test_clean_frees_downloads_and_old_runtimes_but_never_run_data(tmp_path, monkeypatch):
    worker = ready(tmp_path, monkeypatch)
    root = worker.root
    (root / "downloads/linux").mkdir(parents=True)
    (root / "downloads/linux/big.whl").write_bytes(b"x" * 1000)
    (root / "runtimes/old123/python").mkdir(parents=True)
    (root / "runtimes/old123/python/lib").write_bytes(b"y" * 500)
    (root / "artifacts/coordinators/run1").mkdir(parents=True)
    (root / "artifacts/coordinators/run1/ledger.sqlite").write_bytes(b"z" * 300)
    result = worker.clean()
    assert result == {"freedBytes": 1500, "runDataBytes": 300}
    assert worker.paths()["runtime"].exists() and (root / "artifacts/coordinators/run1/ledger.sqlite").exists()
    assert not (root / "runtimes/old123").exists()


def test_the_service_unit_runs_the_command_and_drains_on_stop(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    calls = []

    class Done:
        returncode, stdout = 0, "Linger=no"

    def run(argv, **kwargs):
        calls.append(argv)
        return Done()

    hint = worker_service.Service(run).install("/home/u/.local/bin/heteroes-worker", tmp_path / "worker home")
    unit = worker_service.unit_path().read_text()
    assert 'ExecStart="/home/u/.local/bin/heteroes-worker" run' in unit
    assert f'Environment="HETEROES_WORKER_HOME={tmp_path / "worker home"}"' in unit
    assert "KillSignal=SIGINT" in unit and "KillMode=mixed" in unit and "WantedBy=default.target" in unit
    assert ["systemctl", "--user", "enable", "heteroes-worker.service"] in calls
    assert hint is None and calls[-1][:2] == ["loginctl", "enable-linger"]  # linger switched on without sudo


def test_setup_against_an_older_lab_ends_with_the_web_steps(tmp_path, monkeypatch):
    worker, lab = ready(tmp_path, monkeypatch), FakeLab()
    said = []
    worker.say = said.append

    def older(url, path, token, body, method=None):
        if path == "/api/v1/device/summary":
            raise LabError(404)
        return lab(url, path, token, body, method)

    setup(worker, options(), call=older, sleep=lambda _: None)
    assert "start" in worker.service.calls and "Devices page" in said[-1]


def test_another_gpu_is_its_own_device_sharing_the_runtime_and_model(tmp_path, monkeypatch):
    monkeypatch.setenv("HETEROES_WORKER_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    second = worker_cli.gpu_home(1)
    assert second == tmp_path / "home/gpu1" and worker_cli.gpu_home(None) == tmp_path / "home"
    for name in worker_cli.SHARED:
        assert (second / name).resolve() == (tmp_path / "home" / name).resolve()
    assert not (second / "settings.json").exists()  # its own pairing and token
    unit = worker_service.unit_text("/bin/heteroes-worker", tmp_path / "home", gpu=1)
    assert 'ExecStart="/bin/heteroes-worker" --gpu 1 run' in unit
    assert "CUDA_VISIBLE_DEVICES=1" in unit and "CUDA_DEVICE_ORDER=PCI_BUS_ID" in unit
    assert worker_service.Service(gpu=1).unit == "heteroes-worker-gpu1.service"
    assert worker_service.Service().unit == "heteroes-worker.service"
