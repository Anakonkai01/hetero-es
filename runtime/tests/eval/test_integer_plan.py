"""Decode scheduling depends on dimensions/hardware and must fit a declared workspace before allocation."""

import pytest


def planner():
    from heteroes.strict import integer_plan

    return integer_plan


def test_decode_plan_fills_underused_devices_without_changing_single_row_or_large_grid():
    p = planner()
    small = p.decode_linear_plan(960, 32, 320, 70)
    assert (small.implementation, small.row_tile, small.split_k) == ("mma", 32, 8)
    assert small.partial_bytes == 8 * 32 * 320 * 8
    head = p.decode_linear_plan(960, 32, 49152, 70)
    assert head.split_k == 1 and head.partial_bytes == 0
    single = p.decode_linear_plan(8192, 1, 256, 70)
    assert single.implementation == "simt" and single.split_k == 1 and single.partial_bytes == 0
    assert p.decode_linear_plan(255, 32, 64, 70).split_k == 1


def test_workspace_cap_and_explicit_off_are_applied_before_a_launch():
    p = planner()
    limited = p.decode_linear_plan(8192, 32, 1024, 70, max_partial_bytes=512 * 1024)
    assert limited.split_k == 2 and limited.partial_bytes == 512 * 1024
    tiny = p.decode_linear_plan(8192, 32, 1024, 70, max_partial_bytes=1)
    assert tiny.split_k == 1 and tiny.partial_bytes == 0
    off = p.decode_linear_plan(8192, 32, 1024, 70, target_ctas_per_sm=0)
    assert off.split_k == 1 and off.partial_bytes == 0


@pytest.mark.parametrize(
    "index,bad",
    [(0, 0), (0, 32769), (1, 0), (1, 129), (2, 0), (2, 2**31), (3, 0), (0, True), (1, 1.5), (2, False), (3, -1)],
)
def test_plan_rejects_unsupported_domains(index, bad):
    args = [1024, 32, 4096, 70]
    args[index] = bad
    with pytest.raises(ValueError):
        planner().decode_linear_plan(*args)


@pytest.mark.parametrize(
    "option,value",
    [
        ("max_partial_bytes", 0),
        ("max_partial_bytes", True),
        ("target_ctas_per_sm", -1),
        ("target_ctas_per_sm", True),
        ("target_ctas_per_sm", 65),
    ],
)
def test_invalid_caps_are_not_coerced(option, value):
    with pytest.raises(ValueError):
        planner().decode_linear_plan(1024, 32, 4096, 70, **{option: value})


def test_admission_bound_covers_each_possible_active_batch_and_counts_repeated_projections():
    p = planner()
    shapes = [(960, 320), (960, 320), (2560, 960), (960, 49152)]
    bound = p.decode_workspace_bound(shapes, 32, 70)
    expected = sum(max(p.decode_linear_plan(w, r, n, 70).partial_bytes for r in range(1, 33)) for w, n in shapes)
    assert bound == expected and bound > 0
    assert p.decode_workspace_bound(shapes, 1, 70) == 0
    assert p.decode_workspace_bound(shapes, 32, 70, target_ctas_per_sm=0) == 0
    # The maximum can occur before the last active row count, where a larger split still fits the grid.
    assert p.decode_workspace_bound([(8192, 2048), (8192, 2048)], 96, 70) == 16 * 1024**2
