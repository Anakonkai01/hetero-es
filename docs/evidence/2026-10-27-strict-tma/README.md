# SM120 TMA feasibility: exact memory copies, not yet GEMM acceleration

The next dataflow hypothesis replaces many thread-level tile copy instructions with Tensor Memory
Accelerator (TMA) copies while retaining the original nine integer MMAs and final B22 encoding. NVIDIA's
[SM120 TMA implementation](https://github.com/NVIDIA/cutlass/blob/main/include/cute/arch/copy_sm90_tma.hpp)
uses the CTA-scoped bulk-copy form; this standalone probe verifies that form on the actual 5070 Ti.
It does not call CUTLASS GEMM or change arithmetic.

`tma_copy_v3.py` creates a CUDA tensor map for live U16 storage, uploads its 128-byte descriptor, issues one
2D TMA copy into shared memory, and waits on the transaction barrier before reading it. Waiting is bounded
so an experimental barrier cannot spin indefinitely. No swizzle, repeated pipeline stage or projection
is implemented yet. Descriptor creation and transfer are explicit, rather than assumed free.

**5 tests pass** (`raw/tests-04.log`): full tiles, row/column zero-filled tails, **all 65536 possible U16/FP16
bit encodings** including signed zeros/infinities/NaN payloads, and the opcode audit extension. The all-bit
test reads 32 distinct tiles from one 1024×64 tensor and compares raw integer bits, without FP16 arithmetic.

Earlier receipts are preserved:

- V1 compiles but the stock SASS classifier mistakes `FENCE.VIEW.ASYNC.S` for floating arithmetic because
  its opcode begins with `F`. No GPU copy runs under that failed audit.
- V2 explicitly admits **only that exact memory-fence opcode** through the existing `sass_exact` argument.
  A test still rejects FFMA, FTZ multiplication and unknown fence variants. No audit is disabled and no
  production classifier changes. This stage then exposes CUDA Python's requirement for typed tensor-map
  dimension/box arguments, failing before launch.
- V3 supplies the documented `cuuint64_t`/`cuuint32_t` wrappers; both the initial four tests and the final
  five-test corpus pass. The original sources/logs are unchanged.

Next gates are a producer/consumer swizzle proof, transaction-barrier reuse across pipeline stages, B22 MMA
integration and timings that include real descriptor/staging costs. Activation tensor maps need plane-aware
dimensions so a row tail cannot accidentally read the next radix plane. A projection using TMA will also
need the integer audit to recognize the memory fence explicitly; the successful memory-only audit here
does not automatically qualify a new integer projection module.

## What this does NOT show

There is no TMA GEMM, end-to-end speedup, graph/lifecycle/resource admission, trained candidate parity,
native Windows or SM86 implementation, package or managed qualification yet. TMA support on SM120 does
not authorize selecting it for another GPU. The selected runtime remains `0eb86cb9`, at 71.3% of the matched
vLLM short32 control; the 80% goal is active. No runtime source/default or live lab state was changed.
