"""
The coordinator process: it owns the experiment, the ledger and the canonical weights.

For each generation it
    opens the generation in the ledger (the parent is its own weights) and tells the HTTP server what the job is
    -> waits until every candidate is committed
    -> writes the update record (BEFORE the weights are touched, ADR-002 decision 8)
    -> applies the update to its own model -> marks it applied
    -> publishes the child weights under their SHA-256, so that the workers can synchronize (full sync)

`FAILED` is not the end of a generation (ADR-002 decision 7): after `failed_grace_seconds` without news the coordinator gives up
with a `CoordinatorError`; a late result inside the grace period completes the generation. A failure between the record and the
mark leaves the record in the ledger; the restart procedure that would redo the update from it is NOT written yet.
"""
import time

from heteroes.dispatch import Greedy
from heteroes.es.update import apply_coefficients_
from heteroes.eval.candidate import model_weights_sha256
from heteroes.generation_record import GenerationRecord
from heteroes.ledger import GenerationState, Ledger
from heteroes.manifest import CandidateDescriptor, Recipe, derive_seed
from heteroes.model.schema import ParameterSchema
from heteroes.model.weights_io import publish_weights
from heteroes.http_transport import CoordinatorServer
from heteroes.worker_api import WorkerAPI


class CoordinatorError(Exception):
    """A generation could not be completed."""


class _NoGeneration:
    """What the workers meet before the first generation is open: no work yet, and nothing to deliver to."""

    def handle(self, operation, request):
        if operation == "lease":
            return {"ok": True, "generation_state": "OPEN", "work": None}
        return {"ok": False, "error": {"code": "rejected", "message": "no generation is open"}}


class Coordinator:
    def __init__(self, model, schema: ParameterSchema, recipe: Recipe, ledger: Ledger, models_dir, experiment_id: str,
                 candidates: int, alpha: float, policy_factory=Greedy, lease_seconds: float = 120.0, host: str = "127.0.0.1",
                 port: int = 0, token: str | None = None, poll_seconds: float = 0.2, failed_grace_seconds: float = 5.0,
                 timeout_seconds: float | None = None, log=lambda event: None, timer=time.perf_counter,
                 monotonic=time.monotonic, sleep=time.sleep):
        self.model = model
        self.schema = schema
        self.recipe = recipe
        self.ledger = ledger
        self.models_dir = models_dir
        self.experiment_id = experiment_id
        self.candidates = candidates
        self.alpha = alpha
        self._policy_factory = policy_factory
        self._lease_seconds = lease_seconds
        self._poll = poll_seconds
        self._grace = failed_grace_seconds
        self._timeout = timeout_seconds
        self._log = log
        self._timer = timer
        self._monotonic = monotonic
        self._sleep = sleep
        self.parent_sha256 = model_weights_sha256(model, schema)
        self._parent_published = False
        self.server = CoordinatorServer(_NoGeneration(), job=None, models_dir=models_dir, host=host, port=port, token=token)

    @property
    def url(self) -> str:
        return self.server.url

    def start(self) -> None:
        self.server.start()

    def stop(self) -> None:
        self.server.stop()

    def log(self, event: str, **fields) -> None:
        self._log({"event": event, "t": time.time(), **fields})

    def _job(self, generation: int, policy, state: str = "RUNNING") -> dict:
        return {"experiment_id": self.experiment_id, "generation": generation, "recipe": self.recipe.to_dict(),
                "recipe_hash": self.recipe.hash, "parent_weights_sha256": self.parent_sha256, "candidates": self.candidates,
                "policy": type(policy).__name__, "lease_seconds": self._lease_seconds, "state": state}

    def _wait_until_complete(self, generation: int) -> None:
        started, failed_since = self._monotonic(), None
        while True:
            status = self.ledger.get_generation_status(self.experiment_id, generation)
            now = self._monotonic()
            if status.state is GenerationState.COMPLETE:
                return
            if status.state is GenerationState.FAILED:
                failed_since = now if failed_since is None else failed_since
                if now - failed_since >= self._grace:
                    raise CoordinatorError(f"generation {self.experiment_id}/g{generation} failed: "
                                           f"{', '.join(status.exhausted)} used all attempts")
            else:
                failed_since = None
            if self._timeout is not None and now - started >= self._timeout:
                raise TimeoutError(f"generation {self.experiment_id}/g{generation}: {status.committed} of {status.total} "
                                   f"committed after {self._timeout} s")
            self._sleep(self._poll)

    def run_generation(self, generation: int) -> dict:
        begin = self._timer()
        if not self._parent_published:
            publish_weights(self.model, self.schema, self.models_dir)       # a worker with other weights can synchronize to them
            self._parent_published = True
        parent = self.parent_sha256
        descriptors = [CandidateDescriptor(recipe_hash=self.recipe.hash, parent_weights_sha256=parent,
                                           experiment_id=self.experiment_id, generation=generation, index=index,
                                           seed=derive_seed(self.experiment_id, generation, index))
                       for index in range(self.candidates)]
        self.ledger.open_generation(descriptors)
        policy = self._policy_factory()
        api = WorkerAPI(self.ledger, self.experiment_id, generation, self._lease_seconds, policy)
        self.server.set_generation(api, self._job(generation, policy))
        self.log("generation_open", generation=generation, parent_sha256=parent, candidates=self.candidates)

        self._wait_until_complete(generation)
        waited = self._timer()
        results = self.ledger.get_generation_results(self.experiment_id, generation)
        self.log("generation_complete", generation=generation, rewards=list(results.rewards))

        record = GenerationRecord.from_results(self.experiment_id, generation, results, alpha=self.alpha,
                                               eta=self.recipe.reward_eta)
        self.ledger.record_update(record)                                    # BEFORE the weights are touched
        recorded = self._timer()
        self.log("update_recorded", generation=generation, record_hash=record.hash)

        report = apply_coefficients_(self.model, self.schema, list(record.seeds), record.coefficients, record.alpha,
                                     self.recipe.chunk_elements)
        child = model_weights_sha256(self.model, self.schema)
        self.ledger.mark_applied(self.experiment_id, generation, record.hash, child)
        applied = self._timer()
        self.log("update_applied", generation=generation, child_sha256=child, noop=report.noop, changed=report.changed,
                 applied_l2=report.applied_l2)

        published = publish_weights(self.model, self.schema, self.models_dir)
        if published != child:
            raise CoordinatorError(f"the published weights have the hash {published}, not {child}")
        self.parent_sha256 = child
        done = self._timer()
        self.log("weights_published", generation=generation, child_sha256=child)

        rewards = list(results.rewards)
        summary = {
            "generation": generation, "parent_sha256": parent, "child_sha256": child, "record_hash": record.hash,
            "rewards": rewards, "mean_reward": sum(rewards) / len(rewards), "max_reward": max(rewards),
            "coefficients": list(record.coefficients), "noop": report.noop, "changed": report.changed,
            "applied_l2": report.applied_l2, "requested_l2": report.requested_l2,
            "wait_seconds": waited - begin, "record_seconds": recorded - waited, "update_seconds": applied - recorded,
            "publish_seconds": done - applied, "total_seconds": done - begin,
        }
        self.log("generation_done", **summary)
        return summary

    def finish(self) -> None:
        job = self.server.job
        self.server.set_generation(self.server.api, {"state": "FINISHED"} if job is None else dict(job, state="FINISHED"))

    def run(self, generations: int) -> list[dict]:
        summaries = []
        try:
            for generation in range(generations):
                summaries.append(self.run_generation(generation))
        finally:
            self.finish()
        return summaries
