# Bounded host TMA descriptor templates, 2026-10-27

Unselected extension of the [TMA pipeline](../2026-10-27-strict-tma-pipeline/README.md) against runtime
`0eb86cb9`, on the local RTX 5070 Ti. The five transport/audit helper files are copied unchanged from
that experiment. New host code keeps at most 16 CPU tensor-map templates keyed by layout, patches each
live address with `cuTensorMapReplaceAddress`, and passes aligned maps by value to the existing kernel.
No weight values or GPU descriptor uploads are cached. The supported patch API is documented in the
[CUDA Driver API](https://docs.nvidia.com/cuda/archive/13.2.2/cuda-driver-api/group__CUDA__TENSOR__MEMORY.html).

`raw/tests-01.log`: **2 passing** cases. Two launches and two graph nodes reuse the same CPU map buffers
at distinct tensor addresses, retain independent bindings, and match the original exact B22 output after
live weight sign changes. A second case checks bounded eviction across changing layouts. This is not
full trained candidate acceptance. The initial import failure is retained.

Full synchronized-request pilots, five timed runs after warmup, original Qwen B32 prompts/budgets,
prefix reuse and EOS stopping off:

| Eligible prefill work | short32 token/s | chat128 token/s |
| --- | ---: | ---: |
| All supported projections | 9990.26 | 9992.37 |
| K*N >= 4000000 (MLP only) | 9979.96 | 9975.50 |

Both token hashes match the selected control (`bc4a5504e37c…`, `a9fad5ca48ed…`). All-projection execution
encodes 8 maps, patches 4024 addresses and intercepts 2016 projections. MLP-only execution encodes 6,
patches 1722 and intercepts 864. Reported hashes match every final harness file. Compared with the
selected control near 9866 token/s these are promising small pilots, **not paired ABAB gains**.

**Keep unselected.** If pursued, first measure fresh baseline/candidate ABAB; do not add this gain to
other independent pilots. The inherited private TMA barrier-timeout bit (4) is still an unqualified
infrastructure-error ABI and must be addressed before production selection.

## What this does NOT show

No final runtime selection, complete arithmetic/failure/mutation qualification of the new adapter,
trained canonical +/-/restore or cross-host/native acceptance, package/resource acceptance, learning
effect or 80% result is established. Earlier TMA tests are not rerun or claimed as new tests here.
No deployment, environment or lab-state change occurred.
