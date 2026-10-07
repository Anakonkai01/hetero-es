"""
The model the evaluation runs on (numerical contract section 15).

The weights are FP16 everywhere (the state of the experiment, the thing that is perturbed, restored, updated, hashed and synchronized).
What can differ is the precision of the FORWARD PASS that produces the answers: in FP16 two GPUs, or a padded and an unpadded batch,
round differently and flip the greedy answer whenever the two best scores are closer than that noise (about 1 prompt in 30 in a padded
batch, a few in a thousand between GPUs: `artifacts/experiments/2026-10-07-g6-cross-gpu/`); in FP32 they did not flip in any of the
tests. `EvalModel("float32")` keeps a float32 shadow copy of the model, refreshed from the live FP16 weights (an exact widening, so
nothing is lost) before each evaluation; `EvalModel("float16")` is the live model itself and `refresh()` does nothing.
"""
import copy

import torch

from heteroes.manifest import EVAL_DTYPES


class EvalModel:
    def __init__(self, model, eval_dtype: str = "float16"):
        if eval_dtype not in EVAL_DTYPES:
            raise ValueError(f"eval_dtype must be one of {EVAL_DTYPES}, got {eval_dtype!r}")
        self._live = model
        self.eval_dtype = eval_dtype
        self._shadow = None
        if eval_dtype == "float32":
            # deepcopy keeps the tie between the embedding and the output projection (one Parameter in two modules), `.float()` widens it in place
            self._shadow = copy.deepcopy(model).float()

    @property
    def model(self):
        return self._live if self._shadow is None else self._shadow

    def refresh(self) -> None:
        """Make the evaluation model hold the live weights (call it after the live model changed, before evaluating)."""
        if self._shadow is None:
            return
        with torch.no_grad():
            for live, shadow in zip(self._live.parameters(), self._shadow.parameters(), strict=True):
                shadow.copy_(live)                       # FP16 -> FP32: exact
