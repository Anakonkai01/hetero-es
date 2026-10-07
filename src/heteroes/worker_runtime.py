"""
The life of a worker process (the part of the worker that is not a GPU and not the protocol).

    admit: the coordinator answers, and the recipe of its job is this worker's recipe
    loop:  look at the job; if its parent weights are not the ones in the model, download them (the hash is checked BEFORE the
           model is touched), load them and take them as the new parent; take a turn (`Worker.step`); write down what happened

`WorkerRuntime.run` returns why it stopped: "finished" (the coordinator says the experiment is over), "aborted" (the coordinator
stopped on an error: the experiment did not run to its end), "quarantined" (a restore
failed on this worker: it must be looked at by a human), "unreachable" (the coordinator has not answered for
`max_unreachable_seconds`, if that limit is set) or "stopped" (asked to). One network error is not a reason to die: the worker
waits and asks again. A recipe that changes under a running worker, or a weights file that is not what its name says
after every attempt, ARE reasons to stop: the worker raises. Every event is a plain dict (JSON) handed to `log`.
"""
import hashlib
import http.client
import os
import re
import time
import uuid
from pathlib import Path

from heteroes.executor import CandidateExecutor
from heteroes.http_transport import HttpClient, TransportError, UnauthorizedError
from heteroes.model.weights_io import WeightsFileError, load_weights_, sha256_of_file
from heteroes.worker import StepKind, Worker

_WEIGHTS_FILE = re.compile(r"[0-9a-f]{64}\.bin")


class AdmissionError(Exception):
    """This worker must not work for this job: its recipe is not the job's recipe."""


def _flatten(value, prefix=""):
    if isinstance(value, dict):
        for key, inner in value.items():
            yield from _flatten(inner, f"{prefix}{key}.")
    else:
        yield prefix[:-1], value


def recipe_differences(job_recipe: dict, own_recipe: dict) -> list[str]:
    ours, theirs = dict(_flatten(own_recipe)), dict(_flatten(job_recipe))
    return [f"{key}: coordinator {theirs.get(key)!r}, worker {ours.get(key)!r}"
            for key in sorted(set(ours) | set(theirs)) if ours.get(key) != theirs.get(key)]


def _hash_prefix(path: Path, digest, chunk_bytes: int) -> None:
    with open(path, "rb") as file:
        while chunk := file.read(chunk_bytes):
            digest.update(chunk)


def download_weights(client: HttpClient, sha256: str, directory, chunk_bytes: int = 1 << 20, stats: dict | None = None) -> Path:
    """
    The weights file of that version in `directory`, downloaded if it is not there already and intact. The bytes are hashed
    while they arrive and the file gets its name only if the hash is the name: a wrong transfer leaves nothing.

    A transfer that breaks off (a cable pulled, a coordinator that restarted) leaves `.partial-<sha256>`, and the next call asks the
    server for the rest (`Range: bytes=N-`) after hashing what is already there; a server that answers with the whole file (status
    200) makes it start again from zero. What arrives is checked as a whole at the end, so a damaged partial file can only cost a
    second transfer (the hash is wrong: the partial file is deleted and `WeightsFileError` is raised), never a wrong model.
    If `stats` is given it is filled with `resumed_from_bytes` (what was already there and kept) and `downloaded_bytes` (what was transferred now).
    """
    if stats is not None:
        stats.update({"resumed_from_bytes": 0, "downloaded_bytes": 0})
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    final = directory / f"{sha256}.bin"
    if final.is_file() and sha256_of_file(final) == sha256:
        return final                                            # a corrupted or cut file is simply replaced below
    partial = directory / f".partial-{sha256}"
    digest, offset = hashlib.sha256(), 0
    if partial.is_file():
        offset = partial.stat().st_size
        _hash_prefix(partial, digest, chunk_bytes)
    path = f"/v1/models/{sha256}"
    try:
        try:
            stream = client.open_stream(path, start=offset) if offset else client.open_stream(path)
        except TransportError as error:
            if error.status != 416:
                raise
            # the partial file is as long as the file or longer: either it is complete, or it is not a prefix of it
            if digest.hexdigest() == sha256 and offset:
                os.replace(partial, final)
                if stats is not None:
                    stats["resumed_from_bytes"] = offset
                return final
            partial.unlink(missing_ok=True)
            digest, offset = hashlib.sha256(), 0
            stream = client.open_stream(path)
        with stream as response:
            if offset and getattr(response, "status", None) != 206:
                digest, offset = hashlib.sha256(), 0           # the server sent everything from the start: so do we
            if stats is not None:
                stats["resumed_from_bytes"] = offset
            with open(partial, "ab" if offset else "wb") as file:
                try:
                    while chunk := response.read(chunk_bytes):
                        digest.update(chunk)
                        file.write(chunk)
                        if stats is not None:
                            stats["downloaded_bytes"] += len(chunk)
                except (http.client.HTTPException, OSError) as error:
                    raise TransportError(f"the download of {sha256[:12]} broke off: {error}") from error
        if digest.hexdigest() != sha256:
            partial.unlink(missing_ok=True)
            raise WeightsFileError(f"what arrived for {sha256[:12]} has the hash {digest.hexdigest()[:12]}: wrong hash")
        os.replace(partial, final)
    except (TransportError, KeyboardInterrupt):
        raise                                                   # the partial file stays: the next call continues it
    except BaseException:
        partial.unlink(missing_ok=True)
        raise
    return final


class WorkerRuntime:
    def __init__(self, worker_id: str, client: HttpClient, executor: CandidateExecutor, cache_dir, log=lambda event: None,
                 poll_seconds: float = 0.5, backoff_seconds: float = 2.0, download_attempts: int = 2,
                 max_unreachable_seconds: float | None = None, sleep=time.sleep, wall_clock=time.time, timer=time.perf_counter):
        self.worker_id = worker_id
        self.client = client
        self.executor = executor
        self.cache_dir = Path(cache_dir)
        self._log = log
        self._poll = poll_seconds
        self._backoff = backoff_seconds
        self._download_attempts = download_attempts
        self._max_unreachable = max_unreachable_seconds
        self._sleep = sleep
        self._wall_clock = wall_clock
        self._timer = timer
        self._worker = Worker(worker_id, client, executor, transient_errors=(TransportError,))

    def log(self, event: str, **fields) -> None:
        self._log({"event": event, "t": self._wall_clock(), "worker_id": self.worker_id, **fields})

    def _fetch_job(self) -> dict | None:
        reply = self.client.get_json("/v1/job")
        if reply.get("ok") is not True:
            raise TransportError(f"the coordinator refused to describe the job: {reply!r}")
        return reply["job"]

    def _check_recipe(self, job: dict) -> None:
        own = self.executor.recipe
        if job["recipe_hash"] != own.hash:
            differences = recipe_differences(job.get("recipe", {}), own.to_dict())
            raise AdmissionError("this worker's recipe is not the job's: " + "; ".join(differences or ["(the hash differs)"]))

    def admit(self) -> dict | None:
        """The job, if there is one, after checking that the coordinator is up and that the recipes agree."""
        if self.client.get_json("/v1/health").get("ok") is not True:
            raise TransportError("the coordinator does not answer health")
        job = self._fetch_job()
        if job is not None:
            self._check_recipe(job)
        return job

    def sync(self, job: dict) -> dict:
        """Make the model's weights the job's parent weights (full synchronization). Returns the event it logged."""
        target, previous = job["parent_weights_sha256"], self.executor.parent_sha256
        for attempt in range(1, self._download_attempts + 1):
            start = self._timer()
            try:
                stats = {}
                path = download_weights(self.client, target, self.cache_dir, stats=stats)
                break
            except WeightsFileError:
                if attempt == self._download_attempts:
                    raise
        transferred = self._timer()
        load_weights_(self.executor.model, self.executor.schema, path, target, already_verified=True)      # download_weights hashed every byte
        loaded = self._timer()
        self.executor.reset_parent(target, verified_file=path)     # the model IS the file whose hash was checked: compared, not hashed again
        done = self._timer()
        for old in self.cache_dir.iterdir():
            if (_WEIGHTS_FILE.fullmatch(old.name) and old != path) or (old.name.startswith(".partial-") and old.name != f".partial-{target}"):
                old.unlink()
        (self.cache_dir / f".partial-{target}").unlink(missing_ok=True)
        event = {"from_sha256": previous, "to_sha256": target, "bytes": path.stat().st_size,
                 "transfer_seconds": transferred - start, "load_seconds": loaded - transferred, "rehash_seconds": done - loaded,
                 **stats}                                          # resumed_from_bytes, downloaded_bytes
        self.log("sync", **event)
        return event

    def run(self, stop=None) -> str:
        self.log("start")
        reason = self._loop(stop)
        self.log("exit", reason=reason)
        return reason

    def _loop(self, stop) -> str:
        unreachable_since = None
        while stop is None or not stop.is_set():
            try:
                job = self._fetch_job()
                if job is None:
                    self._sleep(self._poll)
                    continue
                if job.get("state") == "FINISHED":
                    return "finished"
                if job.get("state") == "ABORTED":
                    return "aborted"
                self._check_recipe(job)
                if job["parent_weights_sha256"] != self.executor.parent_sha256:
                    self.sync(job)
                lease_seconds = job.get("lease_seconds")
                if isinstance(lease_seconds, (int, float)) and not isinstance(lease_seconds, bool) and lease_seconds > 0:
                    self._worker.heartbeat_seconds = lease_seconds / 3        # three chances to renew before a lease runs out
                start = self._timer()
                step = self._worker.step(job.get("generation"))
                seconds = self._timer() - start
            except UnauthorizedError as error:
                self.log("unauthorized", error=str(error))
                raise                                                # a wrong token does not get better by waiting: stop and say so
            except TransportError as error:
                self.log("transport_error", error=str(error))
                now = self._timer()
                unreachable_since = now if unreachable_since is None else unreachable_since
                if self._max_unreachable is not None and now - unreachable_since >= self._max_unreachable:
                    return "unreachable"
                self._sleep(self._backoff)
                continue
            unreachable_since = None
            timing = self.executor.last_timing if step.kind in (StepKind.COMMITTED, StepKind.ALREADY_COMMITTED) else None
            self.log("step", kind=step.kind.value, candidate_id=step.candidate_id, code=step.code,
                     failure=None if step.failure is None else step.failure.value,
                     generation_state=None if step.generation_state is None else step.generation_state.value,
                     step_seconds=seconds, timing=timing,
                     coordination_seconds=None if timing is None else seconds - timing["total"])
            if step.kind is StepKind.QUARANTINED:
                return "quarantined"
            if step.kind is StepKind.NO_WORK:
                self._sleep(self._poll)
        return "stopped"
