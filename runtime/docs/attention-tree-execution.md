# Exact grouped attention reductions

The numerical reference remains `pairwise_f32_reference_v1_experimental`. This changes execution of its
adjacent-pair trees, not its rounded operations or model arithmetic. Managed strict remains inactive.

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
