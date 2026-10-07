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

import torch

from heteroes.es.perturb import perturb_model_
from heteroes.es.snapshot import RestoreError, restore_from_snapshot_, take_snapshot
from heteroes.eval.candidate import tensors_sha256
from heteroes.eval.generate import evaluate_model
from heteroes.eval.precision import EvalModel
from heteroes.ledger import FailureKind
from heteroes.manifest import CandidateDescriptor, Recipe
from heteroes.model.schema import ParameterSchema
from heteroes.worker import CandidateFailed


class CandidateExecutor:
    def __init__(self, model, tokenizer, schema: ParameterSchema, recipe: Recipe, clock=time.perf_counter, chunk: int = 1):
        if isinstance(chunk, bool) or not isinstance(chunk, int) or chunk < 1:
            raise ValueError(f"chunk must be an integer of at least 1, got {chunk!r}")
        self.model = model
        self.chunk = chunk                      # prompts per generate() call: an execution choice of this worker, not part of the recipe
        self.tokenizer = tokenizer
        self.schema = schema
        self.recipe = recipe
        self._eval = EvalModel(model, recipe.eval_dtype)     # the model the answers are made on: the live one, or an FP32 copy of it
        self._clock = clock
        self.last_timing: dict[str, float] | None = None
        self.parent_sha256 = ""
        self._snapshot = None
        self.reset_parent()

    def reset_parent(self, expected_sha256: str | None = None, verified_file=None) -> str:
        """
        The weights of the model were replaced (full synchronization): take them as the new parent. The hash is computed from
        the model itself; `expected_sha256`, if given, must be it (else ValueError and nothing changes).

        With `verified_file` (a weights file whose SHA-256 the caller has already checked to be `expected_sha256`, as the download
        does while the bytes arrive) the model is COMPARED with that file instead of hashed: the same guarantee (the model is those
        bytes, so it has that hash), at the speed of memory instead of the speed of SHA-256 (3.6 s per GB on the 1660S's CPU).
        """
        if verified_file is not None and expected_sha256 is None:
            raise ValueError("verified_file needs the expected_sha256 that the file was checked against")
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
        else:
            actual = tensors_sha256(snapshot.tensors)
            if expected_sha256 is not None and actual != expected_sha256:
                raise ValueError(f"the model has the hash {actual}, not the expected {expected_sha256}")
        self._snapshot = snapshot
        self.parent_sha256 = actual
        return actual

    def __call__(self, descriptor: CandidateDescriptor) -> float:
        self.last_timing = None
        if descriptor.recipe_hash != self.recipe.hash:
            raise CandidateFailed(FailureKind.OTHER, f"the job is for another recipe ({descriptor.recipe_hash[:12]}), "
                                                     f"this worker has {self.recipe.hash[:12]}")
        if descriptor.parent_weights_sha256 != self.parent_sha256:
            raise CandidateFailed(FailureKind.OTHER, f"the job is for other parent weights ({descriptor.parent_weights_sha256[:12]}), "
                                                     f"this worker has {self.parent_sha256[:12]}")

        timing: dict[str, float] = {}
        error: BaseException | None = None
        reward = None
        start = mark = self._clock()
        try:
            perturb_model_(self.model, self.schema, descriptor.seed, self.recipe.sigma, self.recipe.chunk_elements)
            now = self._clock()
            timing["perturb"], mark = now - mark, now
            self._eval.refresh()                                # an FP32 copy takes the perturbed weights (nothing to do in FP16)
            reward = float(evaluate_model(self._eval.model, self.tokenizer, chunk=self.chunk).mean_reward)
            now = self._clock()
            timing["rollout"], mark = now - mark, now
        except BaseException as caught:                       # whatever it is, the model must come back first
            error = caught
            mark = self._clock()

        try:
            restore_from_snapshot_(self.model, self.schema, self._snapshot)
        except RestoreError as restore_error:
            raise CandidateFailed(FailureKind.RESTORE_MISMATCH, str(restore_error)) from restore_error
        now = self._clock()
        timing["restore"], timing["total"] = now - mark, now - start

        if error is not None:
            if isinstance(error, torch.cuda.OutOfMemoryError):
                if next(self.model.parameters()).is_cuda:
                    torch.cuda.empty_cache()
                raise CandidateFailed(FailureKind.OUT_OF_MEMORY, str(error)) from error
            raise error
        self.last_timing = timing
        return reward
