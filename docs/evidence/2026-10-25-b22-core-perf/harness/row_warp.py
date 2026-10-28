"""Scratch exact scheduling hypothesis: distribute a 32-row tile across two warp groups."""
from heteroes.eval import integer_cuda as original


class RowWarpKernels(original.IntegerCudaKernels):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self._row_warp_functions=set()

    def _integer_functions(self,width,has_bias=False,row_tile=16,warps=4,split_k=1,*,packed_input=False):
        if row_tile!=32:
            return super()._integer_functions(width,has_bias,row_tile,warps,split_k,packed_input=packed_input)
        name=f'rowwarp2-{self.magnitude_bits}-{width}-{int(has_bias)}-m{row_tile}-w{warps}-s{split_k}-p{int(packed_input)}'
        if name not in self._functions:
            source=original._SOURCE
            start=source.index('extern "C" __global__ void __launch_bounds__(32*WARPS)\ninteger_linear')
            end=source.index('// Same arithmetic, different scheduling:')
            body=source[start:end]
            body=body.replace('__launch_bounds__(32*WARPS)','__launch_bounds__(64*WARPS)')
            body=body.replace('int column=blockIdx.x*(WARPS*8)+warp*8;',
                              'int warp_m=warp/WARPS; warp=warp%WARPS;\n  int column=blockIdx.x*(WARPS*8)+warp*8;')
            body=body.replace('accum[M_GROUPS]', 'accum[M_GROUPS/2]')
            body=body.replace('m<M_GROUPS;', 'm<M_GROUPS/2;')
            body=body.replace('first+m*16+group', 'first+(m*2+warp_m)*16+group')
            source=source[:start]+body+source[end:]
            defines=dict(WIDTH=width,MAGNITUDE_BITS=self.magnitude_bits,DIGITS=2 if self.magnitude_bits==14 else 3,
                         HAS_BIAS=int(has_bias),M_GROUPS=row_tile//16,WARPS=warps,SPLIT_K=split_k,PACKED_INPUT=int(packed_input))
            header=''.join(f'#define {k} {v}\n' for k,v in defines.items())
            self._functions[name]=self._compile(name,header+source,
                ['integer_input','integer_weights','integer_linear','integer_simt','integer_finish'],integer_mma=True)
            self._row_warp_functions.add(id(self._functions[name]['integer_linear']))
        return self._functions[name]

    def _launch(self,function,**kwargs):
        if id(function) in self._row_warp_functions:
            block=kwargs['block'];kwargs['block']=(block[0]*2,block[1])
        return super()._launch(function,**kwargs)
