"""
The coordinator process: it owns the experiment, the ledger and the canonical weights.

For each generation it
    opens the generation in the ledger (the parent is its own weights) and tells the HTTP server what the job is
    -> waits until every candidate is committed
    -> writes the update record (BEFORE the weights are touched, ADR-002 decision 8)
    -> applies the update to its own model -> marks it applied
    -> publishes the child weights under their SHA-256, so that the workers can synchronize (full sync)

`FAILED` is not the end of a generation (ADR-002 decision 7): after `failed_grace_seconds` without news the coordinator gives up
with a `CoordinatorError`; a late result inside the grace period completes the generation. A generation in which nothing is
committed for `stall_seconds` (default five leases, at least a minute) is an error too: a dead worker under a policy that never
hands its candidate to another (B1, B2) would otherwise be waited for forever.

Restart (`recover`): the ledger and the published weights are enough to find the place again. The last generation of the
experiment is one of: not finished (resume it with the weights of its parent), recorded but not applied (apply the STORED record:
the update is deterministic), applied (the child is the current weights; if its file is missing or damaged, recompute it from the
parent and check that it is the hash the ledger marked). `run` calls it first, so a restarted coordinator continues where the
dead one stopped and ends with the weights an uninterrupted run would have.
"""
import time

from heteroes.dispatch import Greedy
from heteroes.es.cuda_ops import apply_coefficients_cuda_
from heteroes.es.update import apply_coefficients_
from heteroes.noise.contracts import CUDA_ENGINE_VERSION
from heteroes.eval.candidate import model_weights_sha256
from heteroes.generation_record import GenerationRecord
from heteroes.ledger import GenerationState, Ledger
from heteroes.manifest import CandidateDescriptor, Recipe, derive_seed
from heteroes.model.schema import ParameterSchema
from heteroes.model.weights_io import WeightsFileError, load_weights_, prepare_publication, prune_published, publish_weights
from heteroes.http_transport import CoordinatorServer
from heteroes.worker_api import WorkerAPI


class CoordinatorError(Exception):
    """A generation could not be completed, or the experiment cannot be taken up again."""


_DEFAULT = object()
MIN_STALL_SECONDS = 60.0
STALL_LEASES = 5


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
                 timeout_seconds: float | None = None, stall_seconds=_DEFAULT, keep_published: int | None = 3, allow_unauthenticated: bool = False, log=lambda event: None, timer=time.perf_counter,
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
        self._stall = max(MIN_STALL_SECONDS, STALL_LEASES * lease_seconds) if stall_seconds is _DEFAULT else stall_seconds
        self._keep_published = keep_published       # how many versions of the weights stay in models_dir (the current one and its ancestors); None: all
        self._recent: list[str] = []                # the hashes published or loaded, newest last
        self._log = log
        self._timer = timer
        self._monotonic = monotonic
        self._sleep = sleep
        self.parent_sha256 = model_weights_sha256(model, schema)
        self._parent_published = False
        self.server = CoordinatorServer(_NoGeneration(), job=None, models_dir=models_dir, host=host, port=port, token=token,
                                        allow_unauthenticated=allow_unauthenticated)

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
        progress, progress_at = None, started
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
            if (status.state, status.committed) != progress:
                progress, progress_at = (status.state, status.committed), now
            elif self._stall is not None and now - progress_at >= self._stall:
                raise CoordinatorError(f"generation {self.experiment_id}/g{generation}: no progress for {self._stall} s "
                                       f"({status.committed} of {status.total} committed): are the workers alive?")
            if self._timeout is not None and now - started >= self._timeout:
                raise TimeoutError(f"generation {self.experiment_id}/g{generation}: {status.committed} of {status.total} "
                                   f"committed after {self._timeout} s")
            self._sleep(self._poll)

    # ---- restart ----------------------------------------------------------------------------------------------------

    def _prune(self, *hashes: str) -> None:
        """Remember these versions as the newest and delete the published files of the older ones (about 1 GB each)."""
        if self._keep_published is None:
            return
        for sha256 in hashes:
            if sha256 in self._recent:
                self._recent.remove(sha256)
            self._recent.append(sha256)
        self._recent = self._recent[-self._keep_published:]
        removed = prune_published(self.models_dir, self._recent)
        if removed:
            self.log("weights_pruned", removed=[name[:-4] for name in removed], kept=list(self._recent))

    def _weights_file(self, sha256: str):
        from pathlib import Path
        return Path(self.models_dir) / f"{sha256}.bin"

    def _load_published(self, sha256: str) -> None:
        """Put the published weights with this hash into the model, or say why that cannot be done."""
        path = self._weights_file(sha256)
        try:
            load_weights_(self.model, self.schema, path, sha256)
        except (OSError, WeightsFileError) as error:
            raise CoordinatorError(f"cannot recover: the published weights {sha256[:12]} are not usable ({error})") from error
        self.parent_sha256 = sha256

    def _apply_record(self, record):
        if self.recipe.engine_version == CUDA_ENGINE_VERSION:                  # the engine that made the noise of the candidates makes that of the update
            return apply_coefficients_cuda_(self.model, self.schema, list(record.seeds), record.coefficients, record.alpha)
        return apply_coefficients_(self.model, self.schema, list(record.seeds), record.coefficients, record.alpha,
                                   self.recipe.chunk_elements)

    def recover(self) -> int:
        """
        Find the place of this experiment in the ledger and the published weights, put the model there and return the number
        of the next generation to run (the unfinished generation itself, if there is one). 0 for a new experiment.
        """
        generations = self.ledger.list_generations(self.experiment_id)
        if not generations:
            return 0
        last = generations[-1]
        if last.recipe_hash != self.recipe.hash:
            raise CoordinatorError(f"the ledger holds generation {last.generation} of another recipe "
                                   f"({last.recipe_hash[:12]}, this is {self.recipe.hash[:12]})")
        number = last.generation
        stored = self.ledger.get_update(self.experiment_id, number)

        if stored is None:                                           # not finished: its candidates are in the ledger, resume it
            if self.parent_sha256 != last.parent_weights_sha256:
                self._load_published(last.parent_weights_sha256)
            self.log("recovered", generation=number, action="resume_generation", parent_sha256=self.parent_sha256)
            self._parent_published = self._weights_file(self.parent_sha256).is_file()
            return number

        child = stored.child_weights_sha256
        if child is not None and self.parent_sha256 == child:        # nothing to do: already there
            return number + 1
        if child is not None:
            try:
                self._load_published(child)
                self.log("recovered", generation=number, action="load_child", child_sha256=child)
                self._parent_published = True
                return number + 1
            except CoordinatorError:
                pass                                                 # missing or damaged: recompute it from the parent below
        if self.parent_sha256 != last.parent_weights_sha256:
            self._load_published(last.parent_weights_sha256)
        report = self._apply_record(stored.record)                   # the stored record, never recomputed (decision O7)
        recomputed = model_weights_sha256(self.model, self.schema)
        if child is not None and recomputed != child:
            raise CoordinatorError(f"cannot recover: applying the stored record of g{number} gives {recomputed[:12]}, "
                                   f"the ledger marked {child[:12]}")
        if child is None:
            self.ledger.mark_applied(self.experiment_id, number, stored.record_hash, recomputed)
        published = publish_weights(self.model, self.schema, self.models_dir)
        if published != recomputed:
            raise CoordinatorError(f"the published weights have the hash {published}, not {recomputed}")
        self.parent_sha256 = recomputed
        self._parent_published = True
        self.log("recovered", generation=number, action="reapply_record", child_sha256=recomputed, noop=report.noop)
        return number + 1

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
        known = [g for g in self.ledger.list_generations(self.experiment_id) if g.generation == generation]
        if known and self.ledger.get_update(self.experiment_id, generation) is not None:
            known = []                                                # already run: open_generation says so ("already open")
        if known:                                                     # a restart: this generation was opened by the coordinator that died
            if known[0].parent_weights_sha256 != parent or known[0].recipe_hash != self.recipe.hash:
                raise CoordinatorError(f"generation {self.experiment_id}/g{generation} is in the ledger with other parent weights or "
                                       f"another recipe: call recover() first")
            self.log("generation_resumed", generation=generation, parent_sha256=parent)
        else:
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

        report = self._apply_record(record)
        # The weights are written and hashed ONCE, into a file that is not visible yet; the ledger is told the child, and only then
        # the file gets its name (a crash in between is recovered: the child is recomputed from the parent and the record).
        publication = prepare_publication(self.model, self.schema, self.models_dir)
        child = publication.sha256
        try:
            self.ledger.mark_applied(self.experiment_id, generation, record.hash, child)
            applied = self._timer()
            self.log("update_applied", generation=generation, child_sha256=child, noop=report.noop, changed=report.changed,
                     applied_l2=report.applied_l2)
            publication.commit()
        except BaseException:
            publication.discard()
            raise
        self.parent_sha256 = child
        self._prune(parent, child)
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

    def finish(self, aborted: bool = False) -> None:
        """Tell the workers that the experiment is over: FINISHED if it ran to its end, ABORTED if it stopped on an error."""
        job = self.server.job
        state = "ABORTED" if aborted else "FINISHED"
        self.server.set_generation(self.server.api, {"state": state} if job is None else dict(job, state=state))

    def run(self, generations: int) -> list[dict]:
        summaries = []
        try:
            for generation in range(self.recover(), generations):
                summaries.append(self.run_generation(generation))
        except BaseException:
            self.finish(aborted=True)             # a failed run must not look like a success to the workers
            raise
        self.finish()
        return summaries
