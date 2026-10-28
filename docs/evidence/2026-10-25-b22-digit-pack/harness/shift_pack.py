"""Scratch-only radix carry execution; the selected B22 implementation is the control."""
from heteroes.eval import integer_cuda as ic


class ShiftPackKernels(ic.IntegerCudaKernels):
    def _integer_functions(self, width, has_bias=False, row_tile=16, warps=4, split_k=1, *, packed_input=False):
        name = f'shiftpack-{self.magnitude_bits}-{width}-bias{int(has_bias)}-m{row_tile}-w{warps}-s{split_k}-p{int(packed_input)}'
        if name not in self._functions:
            old = '''    int low=q&255;
    if(low>=128) low-=256;
    words[d] |= ((unsigned)low&255u) << (8*element);
    q=(q-low)/256; // exact division, including negative values; no signed-left-shift assumption'''
            new = '''    words[d] |= ((unsigned)q&255u) << (8*element);
    int shifted;
    asm("shr.s32 %0, %1, 8;" : "=r"(shifted) : "r"(q+128));
    q=shifted;'''
            assert ic._SOURCE.count(old) == 1
            source = ic._SOURCE.replace(old, new)
            defines = dict(WIDTH=width, MAGNITUDE_BITS=self.magnitude_bits,
                           DIGITS=2 if self.magnitude_bits == 14 else 3, HAS_BIAS=int(has_bias),
                           M_GROUPS=row_tile//16, WARPS=warps, SPLIT_K=split_k,
                           PACKED_INPUT=int(packed_input),
                           WEIGHT_READ32=int(ic.weight_read_plan(self.magnitude_bits,self.arch,self.weight_load)=='paired'))
            header=''.join(f'#define {k} {v}\n' for k,v in defines.items())
            self._functions[name]=self._compile(name,header+source,
                ['integer_input','integer_weights','integer_linear','integer_simt','integer_finish'], integer_mma=True)
        return self._functions[name]
