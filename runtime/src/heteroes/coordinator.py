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
import math
from pathlib import Path

from heteroes.dispatch import Greedy
from heteroes.es.cuda_ops import apply_coefficients_cuda_
from heteroes.es.update import apply_coefficients_
from heteroes.noise.contracts import CUDA_ENGINE_VERSION
from heteroes.eval.candidate import model_weights_sha256
from heteroes.generation_record import GenerationRecord
from heteroes.ledger import GenerationState, Ledger
from heteroes.manifest import CandidateDescriptor, Recipe, derive_seed
from heteroes.v3.antithetic import candidate_seeds
from heteroes.model.schema import ParameterSchema
from heteroes.model.weights_io import (
    WeightsFileError,
    load_weights_,
    prepare_publication,
    prune_published,
    publish_weights,
)
from heteroes.http_transport import CoordinatorServer
from heteroes.worker_api import WorkerAPI


class CoordinatorError(Exception):
    """A generation could not be completed, or the experiment cannot be taken up again."""


class RunCancelled(CoordinatorError):
    """A managed run stopped at a safe boundary, preserving recorded updates."""


class ScoringFailed(CoordinatorError):
    """Recipe v3: the coordinator could not score submitted texts; the generation stops, it is never scored as 0."""


class RunPaused(CoordinatorError):
    """A completed generation was published before opening any further work."""


_DEFAULT = object()
MIN_STALL_SECONDS = 60.0
STALL_LEASES = 5


class _NoGeneration:
    """What the workers meet before the first generation is open: no work yet, and nothing to deliver to."""

    def handle(self, operation, request, authenticated_worker_id=None):
        if (
            authenticated_worker_id is not None
            and operation == "lease"
            and request.get("worker_id") != authenticated_worker_id
        ):
            return {"ok": False, "error": {"code": "forbidden", "message": "Worker identity mismatch"}}
        if operation == "lease":
            return {"ok": True, "generation_state": "OPEN", "work": None}
        return {"ok": False, "error": {"code": "rejected", "message": "no generation is open"}}


class Coordinator:
    def __init__(
        self,
        model,
        schema: ParameterSchema,
        recipe: Recipe,
        ledger: Ledger,
        models_dir,
        experiment_id: str,
        candidates: int,
        alpha: float,
        policy_factory=Greedy,
        lease_seconds: float = 120.0,
        host: str = "127.0.0.1",
        port: int = 0,
        token: str | None = None,
        poll_seconds: float = 0.2,
        failed_grace_seconds: float = 5.0,
        timeout_seconds: float | None = None,
        stall_seconds=_DEFAULT,
        keep_published: int | None = 3,
        allow_unauthenticated: bool = False,
        log=lambda event: None,
        timer=time.perf_counter,
        monotonic=time.monotonic,
        sleep=time.sleep,
        cancel_requested=lambda: False,
        device_tokens=None,
        generation_completed=None,
        generation_started=None,
        pause_requested=lambda: False,
        dataset=None,
        antithetic: bool = False,
        coefficient_rule: str | None = None,
        score=None,
        pinned_weights=(),
        audit_rate=0.05,
        audit_workers=None,
        audit_timeout_seconds=120,
        audit_fault_path=None,
        coefficient_function=None,
        seed_namespace: str | None = None,
        usage_path=None,
        usage_flush_seconds=1.0,
        generation_clock_path=None,
        wall_clock=time.time,
        restore_recovery_path=None,
    ):
        # Recipe v3 (ADR-008): `antithetic` gives pairs (seed, +1), (seed, -1); `coefficient_rule` makes version-2 records;
        # `score(generation, descriptor, completions) -> reward` scores the texts the workers submit, on this process
        if antithetic and candidates % 2:
            raise CoordinatorError("an antithetic population must be even")
        self._antithetic = antithetic
        self._coefficient_rule = coefficient_rule
        self._coefficient_function = coefficient_function  # the loaded code of a python@1 coefficient rule
        self._score = score
        if recipe.to_dict().get("formatVersion") == 3 and score is not None:
            from heteroes.v3.options import validate_audit_rate

            audit_rate = validate_audit_rate(audit_rate)
        self._audit_rate = audit_rate if recipe.to_dict().get("formatVersion") == 3 and score is not None else 0
        self._audit_workers = audit_workers
        self._audit_timeout = audit_timeout_seconds
        self._audit_faults = (
            Path(audit_fault_path) if audit_fault_path is not None else Path(models_dir).parent / "audit-faults.json"
        )
        self._audit_guard = None
        if recipe.to_dict().get("formatVersion") == 3 and score is not None:
            from heteroes.v3 import audit_guard

            # D9: the strict decoder stops at its first audit text mismatch; historical decoders keep their policy
            self._audit_guard = audit_guard.AuditRunGuard(
                ledger,
                experiment_id,
                fault_path=self._audit_faults,
                stop_path=self._audit_faults.with_name("audit-stop.json"),
                stop_on_mismatch=audit_guard.strict_stop_for(recipe),
            )
        if self._audit_rate:
            from heteroes.v3.audit import selected_for_audit

            selected_for_audit("validate", self._audit_rate)
            if not callable(audit_timeout_seconds) and (
                not isinstance(audit_timeout_seconds, (int, float))
                or isinstance(audit_timeout_seconds, bool)
                or not math.isfinite(audit_timeout_seconds)
                or audit_timeout_seconds <= 0
            ):
                raise ValueError("audit timeout must be finite and positive")
        self._api = None
        self.model = model
        self.schema = schema
        self.recipe = recipe
        self.dataset = dataset
        self.ledger = ledger
        self.models_dir = models_dir
        self.experiment_id = experiment_id
        if seed_namespace is not None:
            from heteroes.v3.options import validate_seed_namespace

            validate_seed_namespace(seed_namespace)
            if recipe.to_dict().get("formatVersion") != 3:
                raise ValueError("an explicit seed namespace requires Recipe v3")
        self._seed_namespace = experiment_id if seed_namespace is None else seed_namespace
        self.candidates = candidates
        self.alpha = alpha
        self._policy_factory = policy_factory
        self._lease_seconds = lease_seconds
        self._poll = poll_seconds
        self._grace = failed_grace_seconds
        self._timeout = timeout_seconds
        self._stall = (
            max(MIN_STALL_SECONDS, STALL_LEASES * lease_seconds) if stall_seconds is _DEFAULT else stall_seconds
        )
        self._keep_published = keep_published  # how many versions of the weights stay in models_dir (the current one and its ancestors); None: all
        self._pinned_weights = tuple(pinned_weights)
        self._recent: list[str] = []  # the hashes published or loaded, newest last
        self._log = log
        self._timer = timer
        self._monotonic = monotonic
        self._sleep = sleep
        self.usage = None
        self._usage_sink = None
        if (
            type(usage_flush_seconds) not in (int, float)
            or not math.isfinite(usage_flush_seconds)
            or usage_flush_seconds < 0
        ):
            raise ValueError("usage_flush_seconds must be finite and nonnegative")
        self._usage_flush_seconds = usage_flush_seconds
        # D11: when each generation's hard cap started, kept across restarts so a restart never extends it
        self._clock_path = None if generation_clock_path is None else Path(generation_clock_path)
        self._wall = wall_clock
        from heteroes.restore_recovery import CoordinatorRecoveries

        # D10: workers back from their one restore recovery (None: a restore fault always needs an operator)
        self._recoveries = None if restore_recovery_path is None else CoordinatorRecoveries(restore_recovery_path)
        if usage_path is not None:
            from heteroes.v3.usage import UsageStore
            from heteroes.v3.usage_queue import BoundedUsageSink

            self.usage = UsageStore(usage_path)
            self._usage_sink = BoundedUsageSink(self.usage.record)
        self._cancel_requested = cancel_requested
        self._pause_requested = pause_requested
        self._generation_completed = generation_completed
        self._generation_started = generation_started
        self.parent_sha256 = model_weights_sha256(model, schema)
        self._parent_published = False
        self.server = CoordinatorServer(
            _NoGeneration(),
            job=None,
            models_dir=models_dir,
            host=host,
            port=port,
            token=token,
            allow_unauthenticated=allow_unauthenticated,
            device_tokens=device_tokens,
        )

    @property
    def url(self) -> str:
        return self.server.url

    def start(self) -> None:
        self.server.start()

    def stop(self) -> None:
        self.server.stop()
        if self._usage_sink is not None:
            self._usage_sink.close(self._usage_flush_seconds)

    def set_members(self, members, device_tokens=None) -> None:
        """At a generation boundary (elastic membership, ADR-009): who may audit, and which per-device credentials the
        server accepts. Who may lease is the policy's business (`AdmittedOnly`), built for each generation."""
        members = sorted(members)
        if not members:
            raise ValueError("an experiment needs at least one member")
        if self._audit_workers is not None:
            self._audit_workers = members
        if device_tokens is not None:
            self.server.set_device_tokens(device_tokens)

    def log(self, event: str, **fields) -> None:
        self._log({"event": event, "t": time.time(), **fields})

    def _job(self, generation: int, policy, state: str = "RUNNING") -> dict:
        return {
            "experiment_id": self.experiment_id,
            "generation": generation,
            "recipe": self.recipe.to_dict(),
            "recipe_hash": self.recipe.hash,
            "parent_weights_sha256": self.parent_sha256,
            "candidates": self.candidates,
            "policy": type(policy).__name__,
            "lease_seconds": self._lease_seconds,
            "state": state,
            **({"usageReporting": True} if self.usage is not None else {}),
            "progressReporting": True,
            **(
                {"generationContext": self.recipe.context(self.dataset, generation)} if self.dataset is not None else {}
            ),
        }

    def _limit(self, value, generation):
        """A fixed number of seconds, None, or a function of the generation (derived from measured speeds, ADR-009)."""
        return value(generation) if callable(value) else value

    def _cap_started(self, generation: int, now: float) -> float:
        """The monotonic time this generation's hard cap counts from: the first start, not the latest restart (D11)."""
        if self._clock_path is None:
            return now
        import json

        key = f"{self.experiment_id}/g{generation}"
        clock = json.loads(self._clock_path.read_text()) if self._clock_path.exists() else {}
        wall = self._wall()
        if key not in clock:
            clock[key] = wall
            temporary = self._clock_path.with_name(self._clock_path.name + ".tmp")
            temporary.write_text(json.dumps(clock, sort_keys=True) + "\n")
            temporary.replace(self._clock_path)
        return now - max(0.0, wall - clock[key])

    def _wait_until_complete(self, generation: int) -> None:
        started, failed_since = self._monotonic(), None
        capped = self._cap_started(generation, started)
        progress, progress_at = None, started
        limit = self._limit(self._timeout, generation)
        while True:
            self._check_cancel()
            if self._api is not None and self._api.scoring_error is not None:
                raise ScoringFailed(f"generation {self.experiment_id}/g{generation}: {self._api.scoring_error}")
            if getattr(self._api, "fatal_error", None):
                raise CoordinatorError(self._api.fatal_error)
            status = self.ledger.get_generation_status(self.experiment_id, generation)
            now = self._monotonic()
            if status.state is GenerationState.COMPLETE:
                return
            if status.state is GenerationState.FAILED:
                failed_since = now if failed_since is None else failed_since
                if now - failed_since >= self._grace:
                    raise CoordinatorError(
                        f"generation {self.experiment_id}/g{generation} failed: "
                        f"{', '.join(status.exhausted)} used all attempts"
                    )
            else:
                failed_since = None
            # a heartbeat or a new lease is progress too: a long candidate on a slow GPU is alive (ADR-009)
            moving = (status.state, status.committed, getattr(self._api, "activity", None))
            if moving != progress:
                progress, progress_at = moving, now
            elif self._stall is not None and now - progress_at >= self._stall:
                raise CoordinatorError(
                    f"generation {self.experiment_id}/g{generation}: no progress for {self._stall} s "
                    f"({status.committed} of {status.total} committed): are the workers alive?"
                )
            if limit is not None and now - capped >= limit:
                raise TimeoutError(
                    f"generation {self.experiment_id}/g{generation}: {status.committed} of {status.total} "
                    f"committed after {limit} s (the hard cap counts from the generation's first start)"
                )
            self._sleep(self._poll)

    def _check_cancel(self):
        if self._cancel_requested():
            raise RunCancelled("run cancelled before recording the next update")
        if self._audit_guard is not None and self._audit_guard.fatal_error:
            raise CoordinatorError(self._audit_guard.fatal_error)

    # ---- restart ----------------------------------------------------------------------------------------------------

    def _prune(self, *hashes: str) -> None:
        """Remember these versions as the newest and delete the published files of the older ones (about 1 GB each)."""
        if self._keep_published is None:
            return
        for sha256 in hashes:
            if sha256 in self._recent:
                self._recent.remove(sha256)
            self._recent.append(sha256)
        self._recent = self._recent[-self._keep_published :]
        removed = prune_published(self.models_dir, [*self._recent, *self._pinned_weights])
        if removed:
            self.log("weights_pruned", removed=[name[:-4] for name in removed], kept=list(self._recent))

    def _register_update(self, record, child_sha256: str) -> None:
        """Serve the update (`GET /v1/updates/<parent>`): a worker that is one or a few generations behind can replay it instead of downloading the weights."""
        self.server.updates[record.parent_weights_sha256] = {
            "record_json": record.to_json(),
            "record_hash": record.hash,
            "child_weights_sha256": child_sha256,
        }

    def _weights_file(self, sha256: str):
        from pathlib import Path

        return Path(self.models_dir) / f"{sha256}.bin"

    def _load_published(self, sha256: str) -> None:
        """Put the published weights with this hash into the model, or say why that cannot be done."""
        path = self._weights_file(sha256)
        try:
            load_weights_(self.model, self.schema, path, sha256)
        except (OSError, WeightsFileError) as error:
            raise CoordinatorError(
                f"cannot recover: the published weights {sha256[:12]} are not usable ({error})"
            ) from error
        self.parent_sha256 = sha256

    def _momentum_history(self, generation, window):
        """The merged inputs of the window's earlier generations, newest first, from their recorded updates."""
        history = []
        for earlier in range(generation - 1, max(-1, generation - window), -1):
            stored = self.ledger.get_update(self.experiment_id, earlier)
            if stored is None:
                raise CoordinatorError(f"momentum needs the update record of generation {earlier}")
            history.append(stored.record.history_entry())
        return history

    def _model_on_gpu(self):
        return next(self.model.parameters()).is_cuda

    def _apply_record(self, record):
        seeds, coefficients = record.update_inputs()  # antithetic pairs merged; a version-1 record passes unchanged
        if (
            self.recipe.engine_version == CUDA_ENGINE_VERSION
        ):  # the engine that made the noise of the candidates makes that of the update
            return apply_coefficients_cuda_(self.model, self.schema, seeds, coefficients, record.alpha)
        return apply_coefficients_(
            self.model,
            self.schema,
            seeds,
            coefficients,
            record.alpha,
            self.recipe.chunk_elements,
            engine=self.recipe.engine_version,
        )

    def recover(self) -> int:
        """
        Find the place of this experiment in the ledger and the published weights, put the model there and return the number
        of the next generation to run (the unfinished generation itself, if there is one). 0 for a new experiment.
        """
        generations = self.ledger.list_generations(self.experiment_id)
        if not generations:
            return 0
        for old in generations:  # the updates of the past stay available to a worker that restarts behind
            stored_old = self.ledger.get_update(self.experiment_id, old.generation)
            if stored_old is not None and stored_old.child_weights_sha256 is not None:
                self._register_update(stored_old.record, stored_old.child_weights_sha256)
        last = generations[-1]
        if last.recipe_hash != self.recipe.hash:
            raise CoordinatorError(
                f"the ledger holds generation {last.generation} of another recipe "
                f"({last.recipe_hash[:12]}, this is {self.recipe.hash[:12]})"
            )
        number = last.generation
        stored = self.ledger.get_update(self.experiment_id, number)

        if stored is None:  # not finished: its candidates are in the ledger, resume it
            if self.parent_sha256 != last.parent_weights_sha256:
                self._load_published(last.parent_weights_sha256)
            self.log("recovered", generation=number, action="resume_generation", parent_sha256=self.parent_sha256)
            self._parent_published = self._weights_file(self.parent_sha256).is_file()
            return number

        child = stored.child_weights_sha256
        if child is not None and self.parent_sha256 == child:  # nothing to do: already there
            return number + 1
        if child is not None:
            try:
                self._load_published(child)
                self.log("recovered", generation=number, action="load_child", child_sha256=child)
                self._parent_published = True
                return number + 1
            except CoordinatorError:
                pass  # missing or damaged: recompute it from the parent below
        if self.parent_sha256 != last.parent_weights_sha256:
            self._load_published(last.parent_weights_sha256)
        report = self._apply_record(stored.record)  # the stored record, never recomputed (decision O7)
        recomputed = model_weights_sha256(self.model, self.schema)
        if child is not None and recomputed != child:
            raise CoordinatorError(
                f"cannot recover: applying the stored record of g{number} gives {recomputed[:12]}, "
                f"the ledger marked {child[:12]}"
            )
        if child is None:
            self.ledger.mark_applied(self.experiment_id, number, stored.record_hash, recomputed)
        published = publish_weights(self.model, self.schema, self.models_dir)
        if published != recomputed:
            raise CoordinatorError(f"the published weights have the hash {published}, not {recomputed}")
        self.parent_sha256 = recomputed
        self._parent_published = True
        self._register_update(stored.record, recomputed)
        self.log("recovered", generation=number, action="reapply_record", child_sha256=recomputed, noop=report.noop)
        return number + 1

    def run_generation(self, generation: int) -> dict:
        self._check_cancel()
        begin = self._timer()
        if self.dataset is not None:
            context = self.recipe.context(self.dataset, generation)
            self.ledger.freeze_generation_context(self.experiment_id, generation, context)
            self.log("generation_inputs_frozen", **context)
        if not self._parent_published:
            publish_weights(
                self.model, self.schema, self.models_dir
            )  # a worker with other weights can synchronize to them
            self._parent_published = True
        parent = self.parent_sha256
        descriptors = [
            CandidateDescriptor(
                recipe_hash=self.recipe.hash,
                parent_weights_sha256=parent,
                experiment_id=self.experiment_id,
                generation=generation,
                index=index,
                seed=seed,
                sign=sign,
            )
            # without antithetic pairs these are derive_seed(experiment, generation, index) with sign +1, as before
            for index, (seed, sign) in enumerate(
                candidate_seeds(self._seed_namespace, generation, self.candidates, self._antithetic)
            )
        ]
        known = [g for g in self.ledger.list_generations(self.experiment_id) if g.generation == generation]
        if known and self.ledger.get_update(self.experiment_id, generation) is not None:
            known = []  # already run: open_generation says so ("already open")
        if known:  # a restart: this generation was opened by the coordinator that died
            if known[0].parent_weights_sha256 != parent or known[0].recipe_hash != self.recipe.hash:
                raise CoordinatorError(
                    f"generation {self.experiment_id}/g{generation} is in the ledger with other parent weights or "
                    f"another recipe: call recover() first"
                )
            self.log("generation_resumed", generation=generation, parent_sha256=parent)
        else:
            self.ledger.open_generation(descriptors)
        policy = self._policy_factory()
        api = WorkerAPI(
            self.ledger,
            self.experiment_id,
            generation,
            self._lease_seconds,
            policy,
            cancel_requested=self._cancel_requested,
            scorer=None
            if self._score is None
            else (lambda descriptor, texts: self._score(generation, descriptor, texts)),
            usage_sink=self._usage_sink,
            allowed_chunks=getattr(self.recipe, "chunks", ()) if len(getattr(self.recipe, "chunks", ())) > 1 else (),
            recoveries=self._recoveries,
        )
        if self.recipe.to_dict().get("formatVersion") == 3 and self._score is not None:
            from heteroes.v3.audit import AuditAPI

            api = AuditAPI(
                api,
                self.ledger,
                self.experiment_id,
                generation,
                rate=self._audit_rate,
                workers=self._audit_workers,
                lease_seconds=self._lease_seconds,
                clock=time.time,
                fault_path=self._audit_faults,
                state_path=self._audit_faults.parent / "audit-state" / f"g{generation}.json",
                guard=self._audit_guard,
                log=lambda event: self.log(**event),
                cancel_requested=self._cancel_requested,
            )
        self._api = api
        self.server.set_generation(api, self._job(generation, policy))
        self.log("generation_open", generation=generation, parent_sha256=parent, candidates=self.candidates)

        self._wait_until_complete(generation)
        self._check_cancel()
        self._drain_audits(generation, api, policy)
        waited = self._timer()
        results = self.ledger.get_generation_results(self.experiment_id, generation)
        self.log("generation_complete", generation=generation, rewards=list(results.rewards))

        # a Recipe v3 plan may schedule alpha and add momentum; the record carries the values, so nobody recomputes them
        alpha_at, update_rule = getattr(self.recipe, "alpha_at", None), getattr(self.recipe, "update_rule", None)
        record = GenerationRecord.from_results(
            self.experiment_id,
            generation,
            results,
            alpha=self.alpha if alpha_at is None else alpha_at(generation),
            eta=self.recipe.reward_eta,
            coefficient_rule=self._coefficient_rule,
            update_rule=update_rule,
            momentum_history=None if update_rule is None else self._momentum_history(generation, update_rule["window"]),
            function=self._coefficient_function,
        )
        self._check_cancel()  # last cooperative boundary before write-ahead commit
        if self._audit_guard is None:
            self.ledger.record_update(record)  # BEFORE the weights are touched
        else:
            from heteroes.v3.audit_guard import AuditStopped

            try:
                self._audit_guard.record_update(record)
            except AuditStopped as error:
                raise CoordinatorError(str(error)) from error
        recorded = self._timer()
        self.log("update_recorded", generation=generation, record_hash=record.hash)

        report = self._apply_record(record)
        # Usage bills only the synchronized update; publication below writes and hashes the weights on disk.
        on_gpu = self._model_on_gpu()
        if on_gpu:
            import torch

            torch.cuda.synchronize()
        update_gpu_seconds = self._timer() - recorded if on_gpu else 0.0
        # The weights are written and hashed ONCE, into a file that is not visible yet; the ledger is told the child, and only then
        # the file gets its name (a crash in between is recovered: the child is recomputed from the parent and the record).
        publication = prepare_publication(self.model, self.schema, self.models_dir)
        child = publication.sha256
        try:
            self.ledger.mark_applied(self.experiment_id, generation, record.hash, child)
            applied = self._timer()
            self.log(
                "update_applied",
                generation=generation,
                child_sha256=child,
                noop=report.noop,
                changed=report.changed,
                applied_l2=report.applied_l2,
            )
            publication.commit()
            self._register_update(record, child)
        except BaseException:
            publication.discard()
            raise
        self.parent_sha256 = child
        self._prune(parent, child)
        done = self._timer()
        self.log("weights_published", generation=generation, child_sha256=child)

        rewards = list(results.rewards)
        summary = {
            "generation": generation,
            "parent_sha256": parent,
            "child_sha256": child,
            "record_hash": record.hash,
            "rewards": rewards,
            "mean_reward": sum(rewards) / len(rewards),
            "max_reward": max(rewards),
            "coefficients": list(record.coefficients),
            "noop": report.noop,
            "changed": report.changed,
            "applied_l2": report.applied_l2,
            "requested_l2": report.requested_l2,
            "wait_seconds": waited - begin,
            "record_seconds": recorded - waited,
            "update_seconds": applied - recorded,
            "publish_seconds": done - applied,
            "total_seconds": done - begin,
        }
        if hasattr(api, "audit_summary"):
            summary["audits"] = api.audit_summary()
        if self.usage is not None:
            try:
                self._usage_sink.flush(self._usage_flush_seconds)
                self.usage.record_update(generation, update_gpu_seconds)
                with self.ledger._lock:
                    audits = self.ledger._db.execute(
                        "SELECT count(*) FROM audit JOIN candidate USING(candidate_id) WHERE generation=?",
                        (generation,),
                    ).fetchone()[0]
                summary["usage"] = self.usage.summary(
                    generation, expected_candidates=self.candidates, expected_audits=audits, expected_updates=1
                )
                summary["usage"]["delivery"] = self._usage_sink.status()
                summary["usage"]["partial"] |= summary["usage"]["delivery"]["partial"]
            except Exception:
                summary["usage"] = {"partial": True, "unavailable": True}
        self.log("generation_done", **summary)
        return summary

    def _drain_audits(self, generation, api, policy):
        if not self._audit_rate or api.drain_closed:
            return
        deadline = self._monotonic() + self._limit(self._audit_timeout, generation)
        self.server.set_generation(api, self._job(generation, policy, "AUDITING"))
        while api.pending:
            self._check_cancel()
            if api.fatal_error:
                raise CoordinatorError(api.fatal_error)
            if len(api.available_workers) < 2 or self._monotonic() >= deadline:
                reason = "insufficient_workers" if len(api.available_workers) < 2 else "timeout"
                api.close_drain(reason)
                self.log(
                    "audit_incomplete",
                    generation=generation,
                    pending=api.pending,
                    reason=reason,
                )
                break
            self._sleep(self._poll)
        if api.fatal_error:
            raise CoordinatorError(api.fatal_error)
        if not api.drain_closed:
            api.close_drain("complete")

    def finish(self, aborted: bool = False, cancelled: bool = False) -> None:
        """Tell the workers that the experiment is over: FINISHED if it ran to its end, ABORTED if it stopped on an error."""
        job = self.server.job
        state = "CANCELLED" if cancelled else "ABORTED" if aborted else "FINISHED"
        quarantined = {q.worker_id for q in self.ledger.list_quarantined()}
        if self._api is not None and self._audit_rate:
            quarantined |= self._api.quarantined_workers
        self.server.set_generation(
            self.server.api,
            {"state": state} if job is None else dict(job, state=state, quarantined_workers=sorted(quarantined)),
        )

    def run(self, generations: int) -> list[dict]:
        summaries = []
        try:
            for generation in range(self.recover(), generations):
                self._check_cancel()
                if generation > 0 and self._pause_requested():
                    raise RunPaused("paused after a published generation")
                if self._generation_started is not None:
                    self._generation_started(generation)
                summaries.append(self.run_generation(generation))
                if self._generation_completed is not None:
                    self._generation_completed(summaries[-1])
            self._check_cancel()
        except RunCancelled:
            self.finish(cancelled=True)
            raise
        except RunPaused:
            self.finish()  # Workers restore and exit normally at this barrier.
            raise
        except BaseException:
            self.finish(aborted=True)  # a failed run must not look like a success to the workers
            raise
        self.finish()
        return summaries
