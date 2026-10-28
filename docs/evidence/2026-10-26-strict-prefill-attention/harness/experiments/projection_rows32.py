"""Scratch only: change the prefill tile aspect ratio from 32x64 to 64x32 (same number of output elements)."""
import inspect,textwrap,types
from heteroes.eval import integer_cuda as ic

def install(kernels):
    source=textwrap.dedent(inspect.getsource(ic.IntegerCudaKernels._linear))
    assert source.count('row_tile not in (16, 32)')==1
    source=source.replace('row_tile not in (16, 32)','row_tile not in (16, 32, 64)')
    old='row_tile = (16 if rows <= 16 else 32) if row_tile is None else row_tile'
    assert source.count(old)==1
    source=source.replace(old,'row_tile = (64 if rows >= 64 else 16 if rows <= 16 else 32) if row_tile is None else row_tile\n'
                         '    if row_tile == 64: stream_columns = 32')
    namespace=dict(vars(ic))
    exec(source,namespace)
    kernels._linear=types.MethodType(namespace['_linear'],kernels)
