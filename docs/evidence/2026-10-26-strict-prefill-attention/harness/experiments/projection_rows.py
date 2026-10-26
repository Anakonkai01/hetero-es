"""Scratch only: change the prefill tile aspect ratio from 32x64 to 64x32 (same number of output elements)."""
import inspect,textwrap,types
from heteroes.eval import integer_cuda as ic

def install(kernels, columns=64):
    source=textwrap.dedent(inspect.getsource(ic.IntegerCudaKernels._linear))
    assert source.count('row_tile not in (16, 32)')==1
    source=source.replace('row_tile not in (16, 32)','row_tile not in (16, 32, 64)')
    old='row_tile = (16 if rows <= 16 else 32) if row_tile is None else row_tile'
    assert source.count(old)==1
    source=source.replace(old,'row_tile = (64 if rows >= 64 else 16 if rows <= 16 else 32) if row_tile is None else row_tile\n'
                         f'    if row_tile == 64: stream_columns = {columns}')
    if columns==64:
        old='integers=(rows, outputs),\n    )'
        assert source.count(old)==1
        source=source.replace(old,'integers=(rows, outputs),\n        shared=60*1024 if row_tile==64 and entry=="integer_stream" else 0,\n    )')
        compile_original=kernels._compile
        def compile_dynamic(name,code,entries,**kwargs):
            if 'integer_stream' in entries:
                old='__shared__ __align__(16) unsigned char weights_shared[STAGES][W_STAGE];\n  __shared__ __align__(16) unsigned char inputs_shared[STAGES][A_STAGE];'
                assert code.count(old)==1
                code=code.replace(old,'extern __shared__ __align__(16) unsigned char buffer[];\n'
                                  '  auto weights_shared=reinterpret_cast<unsigned char (*)[W_STAGE]>(buffer);\n'
                                  '  auto inputs_shared=reinterpret_cast<unsigned char (*)[A_STAGE]>(buffer+STAGES*W_STAGE);')
            result=compile_original(name,code,entries,**kwargs)
            if 'integer_stream' in result:
                driver=kernels._driver
                ic.sc._check(driver.cuFuncSetAttribute(result['integer_stream'],driver.CUfunction_attribute.CU_FUNC_ATTRIBUTE_MAX_DYNAMIC_SHARED_SIZE_BYTES,60*1024))
            return result
        kernels._compile=compile_dynamic
    namespace=dict(vars(ic))
    exec(source,namespace)
    kernels._linear=types.MethodType(namespace['_linear'],kernels)
