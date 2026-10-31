import torch
import math
from dataclasses import dataclass
import numpy as np
from heteroes.noise.contracts import check_seed

SUPPORT_DTYPE = torch.float16


def _check_param(param: torch.Tensor) -> None:
    if not param.is_contiguous():
        # torch.reshape would silently write into a copy and leave param unchanged
        raise ValueError("param must be contiguous")
    if param.dtype != SUPPORT_DTYPE:
        raise TypeError(f"param must be {SUPPORT_DTYPE}, got {param.dtype}")


def _check_sigma(sigma: float) -> None:
    if not math.isfinite(sigma):
        raise ValueError("sigma must not be Nan/Inf")


def _check_param_sigma(param: torch.Tensor, sigma: float) -> None:
    _check_param(param)
    _check_sigma(sigma)


@dataclass(frozen=True)
class UpdateReport:
    noop: bool  # no operations
    coefficients: tuple[float, ...]
    requested_l2: float
    applied_l2: float
    changed: int
    numel: int


def _check_coefficients(coefficients) -> np.ndarray:
    # the coefficients of a generation record: a vector of finite numbers that are exactly float32 values
    array = np.asarray(coefficients)
    if array.dtype.kind not in "iuf":
        raise TypeError(f"coefficients must be real numbers, got {array.dtype}")
    if array.ndim != 1:
        raise ValueError("coefficients must be a 1-d vector")
    if array.size == 0:
        raise ValueError("coefficients must not be empty")
    array = array.astype(np.float64)
    if not np.isfinite(array).all():
        raise ValueError("coefficients has a value that is Nan/Inf")
    with np.errstate(over="ignore"):
        as_float32 = array.astype(np.float32)
    if not np.array_equal(as_float32.astype(np.float64), array):
        raise ValueError("every coefficient must be exactly a float32 value (it would be rounded in silence)")
    return as_float32


class NonFiniteUpdateError(RuntimeError):
    """Updated FP16 weights overflowed. In-place model bytes may be dirty; do not mark the record applied."""


def check_update_inputs(candidate_seeds, coefficients, alpha, total_numel, chunk_elements=None):
    """Shared validation/no-op result before either numerical implementation writes its first byte."""
    if not math.isfinite(alpha):
        raise ValueError("alpha must not be Nan/Inf")
    with np.errstate(over="ignore"):
        if not np.isfinite(np.float32(alpha)):
            raise ValueError("alpha must be finite in float32")
    if chunk_elements is not None and not chunk_elements >= 1:
        raise ValueError("chunk_elements must be >=1")
    if len(candidate_seeds) != len(coefficients):
        raise ValueError("length candidate_seeds != lenght rewards")
    for seed in candidate_seeds:
        check_seed(seed)
    if len(set(candidate_seeds)) != len(candidate_seeds):
        raise ValueError("seed being duplicated")
    if not coefficients.any():
        return UpdateReport(True, (0.0,) * len(coefficients), 0.0, 0.0, 0, total_numel)
    return None
