"""
A shared lab from a notebook (owner 2026-10-22: "the notebook is the main way to create an experiment").

    from heteroes.sdk import ESConfig, ESTrainer, reward
    from heteroes.sdk_lab import Dataset, Lab, Model

    lab = Lab.connect("https://lab.heteroes.site", username="me")        # the password is asked, never stored
    model = Model.from_hf("org/model")                                   # pinned to the commit it resolves to
    data = Dataset.from_rows(train=train_rows, validation=val_rows, test=test_rows)   # rows from your own loader
    print(lab.suggest(model, data, max_new_tokens=256))                  # batch and chunks from each GPU's numbers
    run = ESTrainer(ESConfig(model=model, dataset=data, ...), reward_func=my_reward).submit(
        lab, coordinator="5070ti-nhan", workers=["5070ti-nhan", "5070ti-nhut"])
    run.watch()          # the live dashboard; interrupt it at any time, the run goes on
    run.results()

Everything a run depends on is pinned before it starts: the model by its files' SHA-256, the rows by their content hash,
researcher code (reward, coefficient rule, sampler) by the SHA-256 of its source. A model from the hub is a REFERENCE:
each device downloads it and checks every file, so no private network is needed (Tailscale is not the default). Rows
are uploaded to the lab, over its public address when the private route is not reachable (at most 64 MiB per file).
"""

import getpass
import hashlib
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
import time
import urllib.error
import urllib.request

from heteroes.canonical import canonical_json_hash

TERMINAL = ("COMPLETED", "FAILED", "CANCELLED")
SAFE_FILES = ["*.json", "*.safetensors", "*.txt", "*.model", "*.tiktoken", "*.jinja"]  # never code or pickles
FIT = 0.9  # a chunk fits when its estimated peak stays under this share of the GPU's memory


class LabError(RuntimeError):
    pass


class Lab:
    """A signed-in session on a lab: an access token (valid 12 hours) and a workspace, kept in memory only."""

    def __init__(self, url, token, workspace):
        self.url, self.workspace = url.rstrip("/"), workspace
        self._token = token

    def __repr__(self):
        return f"Lab({self.url!r}, workspace={self.workspace!r})"

    @classmethod
    def connect(cls, url="https://lab.heteroes.site", username=None, password=None, workspace=None):
        """Sign in. The password comes from the argument, HETEROES_PASSWORD or a prompt; it is never written anywhere."""
        username = username or input("Lab user name: ")
        password = password or os.environ.get("HETEROES_PASSWORD") or getpass.getpass(f"Password for {username}: ")
        session = _http(url.rstrip("/") + "/api/v1/auth/login", "POST", {"username": username, "password": password})
        spaces = session["workspaces"]
        chosen = next((w for w in spaces if workspace in (None, w["name"], w["workspaceId"])), None)
        if chosen is None:
            raise LabError(f"No workspace {workspace!r}; this account has {[w['name'] for w in spaces]}")
        return cls(url, session["accessToken"], chosen["workspaceId"])

    @classmethod
    def from_session(cls, path=Path.home() / ".config" / "heteroes-demo" / "session.json"):
        """The session `scripts/lab-login.py` saved (0600, outside the repository)."""
        value = json.loads(Path(path).read_text())
        return cls(value["url"], value["token"], value["workspace"])

    def request(self, method, path, body=None, retries=5, sleep=time.sleep):
        """A read is retried through short network failures (the public edge resets a connection now and then)."""
        for attempt in range(retries if method == "GET" else 1):
            try:
                return _http(
                    self.url + path,
                    method,
                    body,
                    {"Authorization": "Bearer " + self._token, "X-Workspace-Id": self.workspace},
                )
            except LabError as error:
                if method != "GET" or attempt == retries - 1 or str(error).startswith("Lab HTTP 4"):
                    raise
            except OSError:
                if method != "GET" or attempt == retries - 1:
                    raise
            sleep(2 * (attempt + 1))

    def upload(self, plan, path):
        from heteroes.v3.lab_cli import USER_AGENT
        from heteroes.study.prepare import private_reachable

        url = plan["url"] if not plan.get("publicUrl") or private_reachable(plan["url"]) else plan["publicUrl"]
        with Path(path).open("rb") as stream:
            request = urllib.request.Request(
                url, method="PUT", data=stream, headers={"User-Agent": USER_AGENT, **plan["headers"]}
            )
            with urllib.request.urlopen(request, timeout=600) as response:
                response.read()

    def devices(self):
        """The GPUs of this workspace, with what the lab knows about each."""
        values = self.request("GET", "/api/v1/workers")
        return [Device.of(v) for v in values if v.get("approvalStatus") != "REVOKED"]

    def device(self, name):
        found = [d for d in self.devices() if name in (d.name, d.worker_id, d.device_id)]
        if not found:  # a CPU-only coordinator is not a GPU worker: look among this account's own devices
            mine = [Device.of(v) for v in self.request("GET", "/api/v1/devices")]
            found = [d for d in mine if name in (d.name, d.worker_id, d.device_id)]
        if len(found) != 1:
            raise LabError(f"{name!r} names {len(found)} devices of this workspace; use its worker id")
        return found[0]

    def model_asset(self, model):
        """The lab's registration of this model (None before the first submit)."""
        return next(
            (
                m
                for m in self.request("GET", "/api/v1/models")
                if m.get("manifestHash") == model.manifest_hash
                and m.get("status") in ("READY", "REGISTERED")
                and (model.source == "UPLOAD" or m.get("source") == "REFERENCE")
            ),
            None,
        )

    def measurements(self, model):
        """{worker id: chunk measurement} from the newest completed qualification of each device for this model."""
        asset = self.model_asset(model)
        if asset is None:
            return {}
        jobs = self.request("GET", f"/api/v1/models/{asset['id']}/qualifications")["jobs"]
        workers = {d.device_id: d.worker_id for d in self.devices()}
        found = {}
        for job in jobs:  # newest first
            worker = workers.get(job["deviceId"])
            if worker and job["status"] == "COMPLETED" and job.get("chunkMemory") and worker not in found:
                found[worker] = job["chunkMemory"]
        return found

    def suggest(self, model, dataset=None, max_new_tokens=256, devices=None, prompt_tokens=None):
        """A batch size and the chunks each GPU may use, from what the GPUs measured for this model (see Suggestion)."""
        from heteroes.v3.options import EXACT_CHUNKS

        chosen = [self.device(d) if isinstance(d, str) else d for d in devices] if devices else self.devices()
        if prompt_tokens is None:
            prompt_tokens = dataset.prompt_tokens() if dataset is not None else 200
        return suggest(
            chosen,
            self.measurements(model),
            EXACT_CHUNKS["float32"],
            prompt_tokens + max_new_tokens,
            dataset.counts.get("train") if dataset is not None else None,
        )

    def qualify(
        self, model, devices, timeout=3600, every=10.0, log=print, sleep=time.sleep, *, engine=None, decoder=None
    ):
        """Qualify every given device for this model that is not yet (the first one builds the lab's reference); a
        device must be ON and idle. Waits for each, one at a time. A strict run (`decoder="strict_b22_v1"`) has its
        own qualification (M4)."""
        from heteroes.noise.contracts import CPU_ENGINES, ENGINE_V2
        from heteroes.product.model_qualification import STRICT_DECODER, qualification_key

        engine = engine or ENGINE_V2
        if engine not in CPU_ENGINES:
            raise ValueError("Unknown CPU noise engine")
        key = qualification_key(engine, decoder)
        asset = self.model_asset(model)
        if asset is None:
            raise LabError("Register the model first (submit does it)")
        seen = set()
        for device in [self.device(d) if isinstance(d, str) else d for d in devices]:
            if device.device_id in seen:
                continue
            seen.add(device.device_id)
            if model.manifest_hash in device.qualified_for(key) or device.cpu_only:
                continue
            log(f"Qualifying {device.name} for {model.id} (a few minutes)…")
            job = self.request(
                "POST",
                f"/api/v1/models/{asset['id']}/qualifications",
                {
                    "deviceId": device.device_id,
                    "noiseEngineVersion": engine,
                    **({"decoder": STRICT_DECODER} if key != engine else {}),
                },
            )
            deadline = time.monotonic() + timeout
            while job["status"] not in TERMINAL:
                if time.monotonic() > deadline:
                    raise LabError(f"Qualification of {device.name} did not finish in {timeout} s")
                sleep(every)
                jobs = self.request("GET", f"/api/v1/models/{asset['id']}/qualifications")["jobs"]
                job = next(j for j in jobs if j["jobId"] == job["jobId"])
            if job["status"] != "COMPLETED":
                raise LabError(f"{device.name} did not qualify: {job['status']} {job.get('errorCode') or ''}")
            log(f"  {device.name}: qualified")

    def submit(self, trainer, coordinator, workers, name=None, directory=None, qualify=True, log=print):
        """Pin the inputs, register them on the lab, qualify the devices, create the experiment and queue it."""
        from heteroes.v3.lab_cli import offer_experiment

        config = trainer.args
        if config.model is None or config.dataset is None:
            raise ValueError("a lab run needs ESConfig(model=Model..., dataset=Dataset...)")
        spec = trainer.lab_spec(name)
        coordinator = self.device(coordinator) if isinstance(coordinator, str) else coordinator
        members = [self.device(w) if isinstance(w, str) else w for w in workers]
        root = Path(directory or Path("heteroes-runs") / canonical_json_hash(spec)[:12])
        root.mkdir(parents=True, exist_ok=True)

        def before_create(asset):
            if qualify:
                self.qualify(
                    config.model,
                    [coordinator, *members],
                    log=log,
                    engine=spec.get("noiseEngineVersion"),
                    decoder=spec.get("decoder"),
                )

        experiment = offer_experiment(
            spec, coordinator.device_id, [m.worker_id for m in members], self, root, before_create
        )
        if experiment["status"] == "DRAFT":
            experiment = self.request("POST", f"/api/v1/experiments/{experiment['experimentId']}/submit")
        run = Run(self, experiment["experimentId"])
        log(f"Queued {experiment['experimentId']}: {run.url}")
        return run

    def run(self, experiment_id):
        return Run(self, experiment_id)


@dataclass
class Device:
    name: str
    worker_id: str
    device_id: str
    gpu: str
    vram_gb: float
    online: bool
    on: bool
    busy: bool
    coordinator: bool
    cpu_only: bool
    qualified: list = field(repr=False, default_factory=list)
    noise_version: str = field(repr=False, default="numpy_pcg64_normal_f32_to_f16_v1")
    qualified_by_engine: dict | None = field(repr=False, default=None)

    def qualified_for(self, engine):
        if self.qualified_by_engine is not None:
            return self.qualified_by_engine.get(engine, [])
        return self.qualified if engine == self.noise_version else []

    @classmethod
    def of(cls, value):
        from heteroes.product.cpu_coordinator import coordinator_only

        profile = value.get("profile") or value.get("selfTest") or {}
        return cls(
            name=value.get("displayName") or value["workerId"],
            worker_id=value["workerId"],
            device_id=value["deviceId"],
            gpu=profile.get("gpuName") or "?",
            vram_gb=round((profile.get("vramTotalMb") or 0) / 1024, 1),
            online=value.get("connectionStatus", value.get("status")) == "ONLINE",
            on=bool(value.get("contributionEnabled")),
            busy=bool(value.get("allocatedTo")),
            coordinator=bool(profile.get("coordinator")),
            cpu_only=coordinator_only(profile),
            qualified=list(profile.get("qualifiedModelHashes") or []),
            noise_version=profile.get("noiseVersion", "numpy_pcg64_normal_f32_to_f16_v1"),
            qualified_by_engine=profile.get("qualifiedModelsByNoiseEngine"),
        )


@dataclass
class Model:
    """A pinned model: its files' SHA-256, and where devices get it (REFERENCE: the hub; UPLOAD: the lab)."""

    id: str
    path: str
    revision: str
    source: str
    manifest: dict = field(repr=False)

    @property
    def manifest_hash(self):
        return canonical_json_hash(self.manifest)

    @classmethod
    def from_hf(cls, repo_id, revision=None):
        """Download (or reuse the cache of) a hub model at one commit; only safe files (no code, no pickles)."""
        from huggingface_hub import snapshot_download

        from heteroes.v3.model import registration_manifest

        path = Path(snapshot_download(repo_id, revision=revision, allow_patterns=SAFE_FILES))
        commit = path.name  # the snapshot folder is named by the commit it resolved to
        return cls(repo_id, str(path), commit, "REFERENCE", registration_manifest(path, repo_id, commit))

    @classmethod
    def from_path(cls, path, model_id):
        """A model of your own (fine-tuned, merged...): its files are uploaded to the lab (the private route is needed)."""
        from heteroes.v3.model import file_manifest, registration_manifest

        revision = canonical_json_hash(file_manifest(path))[:40]
        return cls(model_id, str(path), revision, "UPLOAD", registration_manifest(path, model_id, revision))


@dataclass
class Dataset:
    """Rows frozen to files: what your own loader produced, whatever it read (the hub, files, a database...)."""

    files: dict
    prompt_field: str
    counts: dict
    sha256: str

    @classmethod
    def from_rows(cls, rows=None, *, train=None, validation=None, test=None, prompt_field="prompt", directory=None):
        """Either `rows` (the lab splits them 80/10/10 with a fixed seed) or all three of train, validation and test.
        Each row is a dict with a text `prompt_field`; any other columns go to your reward as they are."""
        splits = {"all": rows} if rows is not None else {"train": train, "validation": validation, "test": test}
        if (rows is None) == (train is None) or any(v is None for v in splits.values()):
            raise ValueError("give rows, or train, validation and test")
        lines = {}
        for name, items in splits.items():
            items = list(items)
            if not items:
                raise ValueError(f"the {name} rows are empty")
            for row in items:
                if not isinstance(row, dict) or not isinstance(row.get(prompt_field), str) or not row[prompt_field]:
                    raise ValueError(f"every row is a dict with a non-empty text {prompt_field!r}")
            lines[name] = "".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in items).encode()
        digest = hashlib.sha256(b"".join(hashlib.sha256(lines[n]).digest() for n in sorted(lines))).hexdigest()
        root = Path(directory or Path("heteroes-data") / digest[:12])
        root.mkdir(parents=True, exist_ok=True)
        files = {}
        for name, content in lines.items():
            files[name] = str(root / f"{name}.jsonl")
            Path(files[name]).write_bytes(content)
        counts = {n: content.count(b"\n") for n, content in lines.items()}
        return cls(files, prompt_field, counts, digest)

    def rows(self, split="train", limit=None):
        out = []
        with open(self.files[split if split in self.files else "all"], encoding="utf-8") as stream:
            for line in stream:
                out.append(json.loads(line))
                if limit and len(out) == limit:
                    break
        return out

    def prompt_tokens(self, sample=200):
        """A generous estimate of prompt length in tokens (about 4 characters per token, plus a chat template)."""
        texts = [r[self.prompt_field] for r in self.rows(limit=sample)]
        return max(len(t) for t in texts) // 3 + 64


@dataclass
class Suggestion:
    batch_size: int
    eval_chunk: int
    eval_chunks: list
    per_device: dict
    notes: list

    def __str__(self):
        lines = [
            f"batch_size={self.batch_size}  eval_chunks={self.eval_chunks}  (eval_chunk={self.eval_chunk})",
            *(f"  {w}: chunk {c}" for w, c in self.per_device.items()),
            *("  " + n for n in self.notes),
        ]
        return "\n".join(lines)


def suggest(devices, measurements, exact_chunks, tokens, train_rows=None, fit=FIT):
    """
    The largest exact chunk each device can hold for `tokens` tokens per prompt, from its measurement: the memory above the
    weights grows with the tokens, so the measured excess is scaled from the measured length. A device without a
    measurement gets the rule a worker applies by itself (its VRAM), and the notes say so. The batch is at least 64 (fewer
    questions make the ranking of candidates mostly luck) and at least the largest chunk, so a large GPU has work for a
    whole call; chunks above the batch would not be used.
    """
    per_device, notes = {}, []
    for device in devices:
        value = measurements.get(device.worker_id)
        if value:
            scale = tokens / (value["promptTokens"] + value["newTokens"])
            usable = [
                item["chunk"]
                for item in value["chunks"]
                if item["ran"]
                and item["chunk"] in exact_chunks
                and value["baseBytes"] + (item["peakBytes"] - value["baseBytes"]) * scale <= fit * value["totalBytes"]
            ]
            per_device[device.worker_id] = max(usable, default=min(exact_chunks))
        else:
            vram = device.vram_gb * 1024
            guess = 64 if vram >= 14_000 else 32 if vram >= 8_000 else 16
            per_device[device.worker_id] = max([c for c in exact_chunks if c <= guess], default=min(exact_chunks))
            notes.append(f"{device.worker_id}: not measured for this model yet (qualify it); chunk from its VRAM")
    chunks = sorted(set(per_device.values())) or [min(exact_chunks)]
    batch = max(64, chunks[-1])
    if train_rows is not None and batch > train_rows:
        batch = train_rows
        notes.append(f"batch limited to the {train_rows} train rows")
    allowed = [c for c in chunks if c <= batch] or [min(exact_chunks)]
    return Suggestion(batch, allowed[0], allowed, per_device, notes)


class Run:
    def __init__(self, lab, experiment_id):
        self.lab, self.id = lab, experiment_id

    def __repr__(self):
        return f"Run({self.id!r}, {self.status()!r})"

    @property
    def url(self):
        return f"{self.lab.url}/experiments/{self.id}"

    def experiment(self):
        return self.lab.request("GET", f"/api/v1/experiments/{self.id}")

    def status(self):
        return self.experiment()["status"]

    def timeline(self):
        return self.lab.request("GET", f"/api/v1/experiments/{self.id}/timeline")

    def watch(self, every=3.0):
        """Draw the live dashboard in the notebook until the run ends. Interrupting the cell stops only the drawing."""
        from heteroes.demo.dashboard import live
        from heteroes.demo.lab import DemoLab

        names = {d.worker_id: d.name for d in self.lab.devices()}
        try:
            return live(DemoLab(api=self.lab), self.id, names, every=every)
        except KeyboardInterrupt:
            print(f"Stopped watching; the run goes on: {self.url}")

    def wait(self, every=15.0, sleep=time.sleep):
        while (status := self.status()) not in TERMINAL:
            sleep(every)
        return status

    def results(self):
        """What the lab shows of the run: status, rewards per generation, validations and work per device. A long run's
        timeline keeps its newest generations whole; the coordinator's ledger has every record."""
        experiment, timeline = self.experiment(), self.timeline()
        events = [e for e in self.lab.request("GET", "/api/v1/events") if e.get("experimentId") == self.id]
        work = {}
        for job in timeline["jobs"]:
            if job.get("status") == "SUCCEEDED":
                work[job["workerId"]] = work.get(job["workerId"], 0) + 1
        return {
            "status": experiment["status"],
            "generations": [
                {"generation": g["index"], "rewardMean": g["rewardMean"], "rewardBest": g["rewardBest"]}
                for g in timeline["generations"]
                if g.get("doneMs")
            ],
            "validation": [
                {
                    "generation": (e.get("details") or {}).get("generation"),
                    "reward": (e.get("details") or {}).get("meanReward"),
                }
                for e in events
                if e.get("eventType") == "validation_completed"
            ],
            "completedPerDevice": work,
            # a long run's timeline keeps only its newest generations: then the counts above are not the whole run
            "partialTimeline": len(timeline["generations"]) < (experiment.get("completedGenerations") or 0),
        }

    def cancel(self):
        return self.lab.request("POST", f"/api/v1/experiments/{self.id}/cancel")


def _http(url, method, body=None, headers=None):
    from heteroes.http_transport import USER_AGENT

    data = None if body is None else json.dumps(body, allow_nan=False).encode()
    request = urllib.request.Request(
        url,
        method=method,
        data=data,
        headers={"Content-Type": "application/json", "User-Agent": USER_AGENT, **(headers or {})},
    )
    try:
        with urllib.request.urlopen(request, timeout=600) as response:
            text = response.read()
            return json.loads(text) if text else None
    except urllib.error.HTTPError as error:
        try:
            detail = json.load(error).get("detail")
        except (ValueError, AttributeError):
            detail = None
        raise LabError(f"Lab HTTP {error.code}: {detail if isinstance(detail, str) else url}") from None
