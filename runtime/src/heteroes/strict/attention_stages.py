"""
GQA decode attention with larger shared-memory K/V stages (SM120 route of `IntegerCudaKernels`).

The original `strict_attention_gqa` kernel stages 32 keys at a time. This variant, derived from its source with checked
text edits, loads KEY_TILE (64 or 128) keys per stage with the same 448-thread CTA and then walks the stage in the
original ordered 32-key score and value subtrees. Every FP32 operation and its order is unchanged, so outputs and error
flags have the original bits (tested against it); only the number of stage barriers falls. A launch is replaced only
where the original would have used the GQA kernel, so the split kernel's range is untouched.

Measured gain and limits: docs/evidence/2026-10-27-strict-final-composed.
"""

from heteroes.strict import strict_cuda as sc

STAGES_VERSION = "gqa_ordered_32_key_subtrees_in_128_key_stages_v1"
KEY_TILE = 128
MAX_SHARED = 96 * 1024


def _once(text, old, new):
    if text.count(old) != 1:
        raise AssertionError(f"key-stage derivation expects exactly one {old[:60]!r}")
    return text.replace(old, new)


def shared_bytes(dim, repeats, max_keys, tile):
    return 4 * ((repeats + tile) * (dim + max(1, dim // 32)) + 2 * repeats * max_keys)


def eligible(arch, dim, repeats, max_keys, tile=KEY_TILE):
    original = shared_bytes(dim, repeats, max_keys, 32)
    return (
        arch == "sm_120"
        and dim == 64
        and 4 <= repeats
        and dim * repeats <= 512
        and sc.gqa_attention_eligible(dim, repeats, original)  # the original launch is the GQA kernel
        and shared_bytes(dim, repeats, max_keys, tile) <= MAX_SHARED
    )


def source(tile):
    assert tile in (64, 128)
    start = sc._OPS_SOURCE.index('extern "C" __global__ void __launch_bounds__(512) strict_attention_gqa(')
    prefix, body = sc._OPS_SOURCE[:start], sc._OPS_SOURCE[start:]
    body = _once(body, "strict_attention_gqa(", "key_stage_attention(")
    body = _once(body, "tile + 32 * padded", "tile + KEY_TILE * padded")
    body = body.replace("float4 staged[4]", "float4 staged[LOADS]")
    body = body.replace("u < 4", "u < LOADS")
    body = body.replace("keys - first < 32 ? keys - first : 32", "keys - first < KEY_TILE ? keys - first : KEY_TILE")
    body = body.replace("first += 32", "first += KEY_TILE")
    body = body.replace("first + 32 < keys", "first + KEY_TILE < keys").replace("first + 32);", "first + KEY_TILE);")
    # scores: each staged block is consumed as consecutive 32-key subtrees
    begin = body.index("    const bool live = score_row < rows;")
    end = body.index("  }\n  fetch(values_base, 0);", begin)
    old = body[begin:end].replace("score_row", "local_row")
    body = (
        body[:begin]
        + "    #pragma unroll 1\n    for(int sub=0;sub<KEY_TILE;sub+=32) {\n      int local_row=score_row+sub;\n"
        + old
        + "    }\n"
        + body[end:]
    )
    # values: the same ordered 32-key value subtrees, pushed one after the other
    begin = body.index("    float group[4];", body.index("  Tree t;"))
    end = body.index("    push(t, group[0], bad);", begin) + len("    push(t, group[0], bad);")
    old = body[begin:end]
    old = old.replace("rows - base", "subtree_rows - base").replace("(rows + 7)", "(subtree_rows + 7)")
    old = old.replace("scores[first + base + item]", "scores[first + sub + base + item]")
    old = old.replace("tile[(base + item) * padded", "tile[(sub + base + item) * padded")
    body = (
        body[:begin]
        + "    #pragma unroll 1\n    for(int sub=0;sub<rows;sub+=32) {\n      int subtree_rows=rows-sub<32 ? rows-sub : 32;\n"
        + old
        + "\n    }"
        + body[end:]
    )
    header = "".join(f"#define {n} 0x{v:08x}u\n" for n, v in sc.reference_constants().items())
    return header + f"#define KEY_TILE {tile}\n#define LOADS {tile // 16}\n" + prefix + body
