"""
What a worker's GPU does for one candidate: the `evaluate(descriptor) -> reward` of `heteroes.worker.Worker`.

    check that the job is for this model -> perturb (sigma and chunk size of the recipe) -> evaluate -> restore, verified bit for bit

A job for another recipe or other parent weights is refused before anything is touched (the worker would otherwise report a
reward for a candidate that is not the one that was asked). The model always comes back to the parent weights, whatever
happens in between. A failure is raised as `CandidateFailed` with its kind and is never a reward: running out of memory is
OUT_OF_MEMORY; a restore that does not give the parent back bit for bit is RESTORE_MISMATCH and wins over any other failure
(the weights are in doubt, so this worker must be put aside); any other exception is a bug and is raised as it is, after the
restore. The parent snapshot is taken once and is valid for every candidate of a generation.

The precision of the forward pass is the recipe's `eval_dtype`: FP16 evaluates the live model; FP32 evaluates a float32 copy that takes the
perturbed weights just before the evaluation (`heteroes.eval.precision`). The weights that are perturbed, restored and hashed stay FP16.
"""

import time
from contextlib import nullcontext
from dataclasses import dataclass

import torch

from heteroes.es.cuda_ops import perturb_model_cuda_
from heteroes.es.perturb import perturb_model_
from heteroes.es.snapshot import RestoreError, restore_from_snapshot_, take_snapshot
from heteroes.eval.candidate import tensors_sha256
from heteroes.eval.generate import evaluate_model
from heteroes.eval.precision import EvalModel, default_chunk
from heteroes.eval.workloads import get_workload
from heteroes.ledger import FailureKind
from heteroes.manifest import CandidateDescriptor, Recipe
from heteroes.model.schema import ParameterSchema
from heteroes.noise.contracts import CUDA_ENGINE_VERSION
from heteroes.worker import CandidateFailed


@dataclass(frozen=True)
class TaskOutcome:
    """What evaluating the task of a recipe gives: the reward of the candidate and the texts it was computed from, in row order."""

    reward: float
    completions: tuple[str, ...]
    token_counts: tuple[int, ...] | None = None


def evaluate_task(recipe, model, tokenizer, chunk: int, rows=None) -> TaskOutcome:
    """
    The one place where the task of a recipe is evaluated: the imported dataset `rows` of a Recipe v2 (greedy accuracy), the
    16 prompts of the contract (arith16) or a long built-in workload. The texts behind the reward are kept, so that they can be
    reported with it. `evaluate_model` and `get_workload` are looked up in this module at call time, so that tests and the
    desktop qualification can replace them.
    """
    if rows is not None:
        from heteroes.study.evaluation import evaluate

        counts = recipe.to_dict().get("formatVersion") == 3
        raw = evaluate(model, tokenizer, rows, recipe.evaluation, chunk, **({"count_tokens": True} if counts else {}))
        return TaskOutcome(
            float(raw["accuracy"]),
            tuple(row["output"] for row in raw["rows"]),
            tuple(row["generatedTokens"] for row in raw["rows"]) if counts else None,
        )
    if recipe.workload_name == "arith16":
        result = evaluate_model(model, tokenizer, chunk=chunk)
    else:
        result = get_workload(recipe.workload_name).evaluate(model, tokenizer, chunk, recipe.decode_engine)
    return TaskOutcome(float(result.mean_reward), tuple(record.output_text for record in result.records))


class ChunkTexts(tuple):
    """Completions with the chunk that produced them (ADR-010)."""

    def __new__(cls, texts, chunk):
        value = super().__new__(cls, texts)
        value.chunk = chunk
        return value


class CandidateExecutor:
    def __init__(
        self,
        model,
        tokenizer,
        schema: ParameterSchema,
        recipe: Recipe,
        clock=time.perf_counter,
        chunk: int | None = None,
        dataset=None,
        return_completions: bool = False,
        phase_trace=None,
    ):
        declared = getattr(
            recipe, "chunk", None
        )  # a Recipe v3 document may fix it: then it is not this worker's choice
        # ADR-010: a recipe may allow several chunks; the one used goes with the result
        allowed = tuple(getattr(recipe, "chunks", ()) or ()) or ((declared,) if declared is not None else ())
        if declared is not None and chunk not in (None, *allowed):
            raise ValueError(f"the recipe allows chunks {allowed}; this worker asked for {chunk!r}")
        self.allowed_chunks = allowed
        if chunk is None:
            # the recipe's, or the exact size for the recipe's precision (FP32: 16, FP16: 1)
            chunk = declared if declared is not None else default_chunk(recipe.eval_dtype)
        if isinstance(chunk, bool) or not isinstance(chunk, int) or chunk < 1:
            raise ValueError(f"chunk must be an integer of at least 1, got {chunk!r}")
        self.model = model
        self.chunk = chunk  # prompts per generate() call: this worker's choice unless the recipe declares it
        self.tokenizer = tokenizer
        self.schema = schema
        self.recipe = recipe
        self.dataset = dataset
        # Recipe v3 (ADR-008 section 7): the call returns the texts, which the coordinator scores, instead of the reward
        self.return_completions = return_completions
        self.effective_sigma = recipe.sigma
        self.batch_rows = None
        self._eval = EvalModel(
            model, recipe.eval_dtype
        )  # the model the answers are made on: the live one, or an FP32 copy of it
        self._clock = clock
        self.phase_trace = phase_trace  # opt-in host telemetry; never part of numerical or retry identity
        self.last_timing: dict[str, float] | None = None
        self.last_completions: tuple[str, ...] | None = None  # the texts behind the last reward; None after a failure
        self.parent_sha256 = ""
        self._snapshot = None
        self.reset_parent()

    def _phase(self, name, descriptor):
        if self.phase_trace is None:
            return nullcontext()
        return self.phase_trace.phase(
            name,
            candidate_id=descriptor.candidate_id,
            generation=descriptor.generation,
            recipe_hash=descriptor.recipe_hash,
            device=str(next(self.model.parameters()).device),
        )

    def set_generation(self, generation, context):
        if getattr(self.recipe, "python_sampler", False):
            # a researcher's sampler ran on the coordinator: its row numbers are taken from the context and checked
            given = context.get("batchIndices") if isinstance(context, dict) else None
            expected = self.recipe.context(self.dataset, generation, given)
        else:
            expected = self.recipe.context(self.dataset, generation)
        if context != expected:
            raise ValueError("Generation batch/sigma context mismatch")
        self.effective_sigma = expected["sigmaFloat32"]
        self.batch_rows = [self.dataset["splits"]["train"][i] for i in expected["batchIndices"]]
        self.generation = generation

    def reset_parent(self, expected_sha256: str | None = None, verified_file=None, trust: bool = False) -> str:
        """
        The weights of the model were replaced (full synchronization): take them as the new parent. The hash is computed from
        the model itself; `expected_sha256`, if given, must be it (else ValueError and nothing changes).

        With `verified_file` (a weights file whose SHA-256 the caller has already checked to be `expected_sha256`, as the download
        does while the bytes arrive) the model is COMPARED with that file instead of hashed: the same guarantee (the model is those
        bytes, so it has that hash), at the speed of memory instead of the speed of SHA-256 (3.6 s per GB on the 1660S's CPU).
        With `trust` (replay, `replay.py`) the model is NOT checked at all: `expected_sha256` becomes its hash on the caller's word.
        """
        if verified_file is not None and expected_sha256 is None:
            raise ValueError("verified_file needs the expected_sha256 that the file was checked against")
        if trust and (expected_sha256 is None or verified_file is not None):
            raise ValueError(
                "trust takes the expected_sha256 as the hash of the model without checking it, and has no verified_file"
            )
        # One copy of the model to the CPU serves both purposes: it IS the snapshot, and the bits to hash or to compare.
        snapshot = take_snapshot(self.model, self.schema)
        if verified_file is not None:
            from heteroes.model.weights_io import tensors_match_file
            from pathlib import Path

            if Path(verified_file).stat().st_size != 2 * sum(tensor.numel() for tensor in snapshot.tensors):
                raise ValueError(f"{verified_file}: the size of the file is not the size of the model")
            if not tensors_match_file(snapshot.tensors, verified_file):
                raise ValueError(f"the model differs from the verified file {Path(verified_file).name}")
            actual = expected_sha256
        elif trust:
            actual = expected_sha256  # replay: the caller TRUSTS the coordinator's hash (a pass over 1 GB is skipped); the weights are the snapshot all the same
        else:
            actual = tensors_sha256(snapshot.tensors)
            if expected_sha256 is not None and actual != expected_sha256:
                raise ValueError(f"the model has the hash {actual}, not the expected {expected_sha256}")
        self._snapshot = snapshot
        self.parent_sha256 = actual
        return actual

    def __call__(self, descriptor: CandidateDescriptor, chunk: int | None = None) -> float:
        """`chunk`: an audit re-runs a candidate at the chunk its first result used (ADR-010); otherwise this worker's."""
        used = self.chunk if chunk is None else chunk
        if self.allowed_chunks and used not in self.allowed_chunks:
            raise CandidateFailed(FailureKind.OTHER, f"chunk {used} is not allowed by the recipe")
        try:
            return self._run(descriptor, used)
        except CandidateFailed as failed:
            declared = getattr(self.recipe, "chunk", None)
            if failed.kind is not FailureKind.OUT_OF_MEMORY or chunk is not None or declared in (None, used):
                raise
            # this device cannot hold the larger chunk: from now on it uses the recipe's own, which every member can
            self.chunk = declared
            return self._run(descriptor, declared)

    def _run(self, descriptor: CandidateDescriptor, chunk: int):
        self.last_timing = None
        self.last_completions = None
        if descriptor.recipe_hash != self.recipe.hash:
            raise CandidateFailed(
                FailureKind.OTHER,
                f"the job is for another recipe ({descriptor.recipe_hash[:12]}), "
                f"this worker has {self.recipe.hash[:12]}",
            )
        if descriptor.parent_weights_sha256 != self.parent_sha256:
            raise CandidateFailed(
                FailureKind.OTHER,
                f"the job is for other parent weights ({descriptor.parent_weights_sha256[:12]}), "
                f"this worker has {self.parent_sha256[:12]}",
            )
        if self.dataset is not None and (self.batch_rows is None or descriptor.generation != self.generation):
            raise CandidateFailed(FailureKind.OTHER, "Generation inputs were not verified")

        timing: dict[str, float] = {}
        error: BaseException | None = None
        reward = None
        measured_cuda = (
            self.return_completions
            and self.recipe.to_dict().get("formatVersion") == 3
            and next(self.model.parameters()).is_cuda
        )
        if measured_cuda:
            torch.cuda.synchronize()
        start = mark = self._clock()
        try:
            # the second candidate of an antithetic pair is perturbed with -sigma (ADR-008 section 5); 1 * sigma is sigma exactly
            scale = descriptor.sign * self.effective_sigma
            with self._phase("perturb", descriptor):
                if self.recipe.engine_version == CUDA_ENGINE_VERSION:
                    perturb_model_cuda_(self.model, self.schema, descriptor.seed, scale)
                else:
                    perturb_model_(
                        self.model,
                        self.schema,
                        descriptor.seed,
                        scale,
                        self.recipe.chunk_elements,
                        engine=self.recipe.engine_version,
                    )
            now = self._clock()
            timing["perturb"], mark = now - mark, now
            with self._phase("refresh", descriptor):
                self._eval.refresh()  # an FP32 copy takes the perturbed weights (nothing to do in FP16)
            # batch_rows is None without a dataset (set_generation needs one), and a dataset job without them is refused above
            with self._phase("rollout", descriptor):
                outcome = evaluate_task(self.recipe, self._eval.model, self.tokenizer, chunk, self.batch_rows)
            reward, completions = outcome.reward, outcome.completions
            now = self._clock()
            timing["rollout"], mark = now - mark, now
        except BaseException as caught:  # whatever it is, the model must come back first
            error = caught
            mark = self._clock()

        try:
            with self._phase("restore", descriptor):
                restore_from_snapshot_(self.model, self.schema, self._snapshot)
        except RestoreError as restore_error:
            raise CandidateFailed(FailureKind.RESTORE_MISMATCH, str(restore_error)) from restore_error
        if measured_cuda:
            torch.cuda.synchronize()
        now = self._clock()
        timing["restore"], timing["total"] = now - mark, now - start

        if error is not None:
            if isinstance(error, torch.cuda.OutOfMemoryError):
                if next(self.model.parameters()).is_cuda:
                    torch.cuda.empty_cache()
                raise CandidateFailed(FailureKind.OUT_OF_MEMORY, str(error)) from error
            raise error
        self.last_timing = timing
        self.last_completions = completions
        if self.return_completions and outcome.token_counts is not None:
            from heteroes.v3.usage import CompletionBatch

            batch = CompletionBatch(
                completions,
                {
                    "formatVersion": 1,
                    "generatedTokens": list(outcome.token_counts),
                    "device": next(self.model.parameters()).device.type,
                    "wallSeconds": timing["total"],
                },
            )
            batch.chunk = chunk if len(self.allowed_chunks) > 1 else None
            return batch
        if self.return_completions and len(self.allowed_chunks) > 1:
            return ChunkTexts(completions, chunk)
        return completions if self.return_completions else reward
