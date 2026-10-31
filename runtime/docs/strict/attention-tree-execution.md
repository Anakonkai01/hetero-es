# Exact grouped attention reductions

> **Status (2026-10-29).** The word `experimental` in identity strings and `hardwareQualified: false` in kernel identities are names and fields inside hashed documents; they are never edited and do not say whether the code is accepted. Acceptance is recorded by receipts. The B22 path described here is the Recipe v3 decoder `strict_b22_v1` ([ADR-013](../adr/ADR-013-strict-b22-recipe-decoder.md), accepted; the default for new GPU runs), and its acceptance checks PASS on SM120, SM86 under WSL2 and native Windows at source `src-18d0b138` ([acceptance STATUS](../../../docs/acceptance/STATUS.md)). Sentences below that say "experimental", "inactive" or "not accepted" describe the state when the note was written, unless a line in this note says otherwise.

The numerical reference remains `pairwise_f32_reference_v1_experimental`. This changes execution of its
adjacent-pair trees, not its rounded operations or model arithmetic. (When this was written managed strict was inactive; it is active for `strict_b22_v1` since D9, 2026-10-27, see [audit-state-v1](../audit-state-v1.md).)

For a positive length `n`, the reference pairs adjacent leaves, carries an unmatched last leaf without an
addition, and repeats. The CUDA binary-counter `Tree` implements the same tree: each occupied slot represents
an aligned power-of-two prefix subtree, and `finish` folds pending subtrees from the smallest/rightmost upward.
Expanding its carry/fold branches does not change that order.

Attention now reduces consecutive groups of eight products into subtree roots before applying `Tree` to those
roots. Eight is a power of two, so every complete group is an aligned reference subtree. The final group uses
the same pruned tree, adding a right child only when that child exists. Replacing these subtrees with their
roots leaves the complete expression tree unchanged. No zero-valued identity node is appended, including for
one-element groups and odd tails. This distinction preserves negative-zero results.

The same argument applies separately to the Q/K dot product (up to 256 channels) and the probability/value
sum (up to 4096 keys). Each original load, signed-zero FTZ boundary, rounded multiply, rounded add and error
check remains. Only the evaluation order of independent subtrees changes. Softmax maximum normalization,
causal masking, exponent polynomial, denominator reduction and reciprocal are unchanged. Causally masked
Q/K products are still computed and checked: a masked intermediate overflow must still fail.

The argument relies on the existing explicit rounded CUDA primitives and instruction audit. Compile flags,
PTX/SASS checks, independent CPU comparisons and architecture acceptance remain required. Code-source hashes
change execution/qualification/profile identities; the arithmetic-reference version does not change.

The dated evidence includes exact symbolic topology comparisons for every length 1..4096, both group sizes
8/16, signed-zero/subnormal/cancellation/tail tests, masked-overflow tests, compiler resources and trained-model
measurements. Symbolic topology equality is not a compiler or hardware theorem. Resource counters are
diagnostic; throughput is measured separately.

Decode already supplies the true prefix length in its range table. `max_context` controls allocation bounds;
this optimization does not remove future-key computations from decode, skip masked checks or alter KV ownership.
