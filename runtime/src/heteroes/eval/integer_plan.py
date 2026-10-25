"""Dimension-only bounded decode scheduling for the exact integer projection contract.

Only decode uses this plan. Prefill retains its existing execution. Split-K changes exact integer scheduling,
never the row scale, quantization, sum or final rounding. Device SM count affects scheduling, not arithmetic.
"""

from collections import Counter
from dataclasses import dataclass
import hashlib
from pathlib import Path

POLICY_VERSION = "occupancy_split_k_v1_experimental"
DEFAULT_PARTIAL_BYTES = 16 * 1024**2
DEFAULT_TARGET_CTAS_PER_SM = 8


def _integer(name, value, minimum=1, maximum=None):
    if type(value) is not int or value < minimum or (maximum is not None and value > maximum):
        raise ValueError(f"Unsupported integer decode {name}")


def validate_target(target):
    _integer("target CTAs per SM", target, 0, 64)


@dataclass(frozen=True)
class DecodeLinearPlan:
    width: int
    rows: int
    outputs: int
    row_tile: int
    split_k: int
    implementation: str
    partial_bytes: int


def decode_linear_plan(
    width,
    rows,
    outputs,
    multiprocessors,
    *,
    max_partial_bytes=DEFAULT_PARTIAL_BYTES,
    target_ctas_per_sm=DEFAULT_TARGET_CTAS_PER_SM,
):
    _integer("width", width, 1, 32768)
    _integer("rows", rows, 1, 128)
    _integer("outputs", outputs, 1, 2**31 - 1)
    _integer("multiprocessors", multiprocessors)
    _integer("partial budget", max_partial_bytes)
    validate_target(target_ctas_per_sm)
    tile, split = (16 if rows <= 16 else 32), 1
    mode = "simt" if rows == 1 else "mma"
    if rows > 1 and width >= 256 and target_ctas_per_sm:
        blocks = ((outputs + 31) // 32) * ((rows + tile - 1) // tile)
        while split < 8 and blocks * split < target_ctas_per_sm * multiprocessors:
            split *= 2
        while split > 1 and (split * rows * outputs * 8 > max_partial_bytes or split > (width + 31) // 32):
            split //= 2
    partial = 0 if split == 1 else split * rows * outputs * 8
    return DecodeLinearPlan(width, rows, outputs, tile, split, mode, partial)


def decode_workspace_bound(
    shapes,
    capacity,
    multiprocessors,
    *,
    max_partial_bytes=DEFAULT_PARTIAL_BYTES,
    target_ctas_per_sm=DEFAULT_TARGET_CTAS_PER_SM,
):
    """Sum independent peak partial payloads over ALL possible active batches, including repeated projections.

    This deliberately assumes no allocator reuse between projection calls. It is an upper tensor-payload
    bound, not total VRAM. Weights/activations and request metadata are counted by the graph's other terms.
    """
    _integer("capacity", capacity, 1, 128)
    if not isinstance(shapes, (tuple, list)) or not shapes:
        raise ValueError("Decode workspace needs nonempty projection shapes")
    for shape in shapes:
        if not isinstance(shape, (tuple, list)) or len(shape) != 2:
            raise ValueError("Decode workspace needs width/output pairs")
        decode_linear_plan(
            shape[0],
            1,
            shape[1],
            multiprocessors,
            max_partial_bytes=max_partial_bytes,
            target_ctas_per_sm=target_ctas_per_sm,
        )
    return sum(
        copies
        * max(
            decode_linear_plan(
                width,
                rows,
                outputs,
                multiprocessors,
                max_partial_bytes=max_partial_bytes,
                target_ctas_per_sm=target_ctas_per_sm,
            ).partial_bytes
            for rows in range(1, capacity + 1)
        )
        for (width, outputs), copies in Counter(tuple(shape) for shape in shapes).items()
    )


def identity():
    return {
        "policy": POLICY_VERSION,
        "rowTiles": [16, 32],
        "maxSplitK": 8,
        "minSplitWidth": 256,
        "maxBatch": 128,
        "singleRow": "simt_split1",
        "sourceSha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    }
