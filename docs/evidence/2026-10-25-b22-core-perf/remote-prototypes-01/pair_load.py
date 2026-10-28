"""Scratch exact two-half load: smaller vectors than the previously rejected four-half load."""
from heteroes.eval import integer_cuda as original


class PairLoadKernels(original.IntegerCudaKernels):
    def _integer_functions(self,width,has_bias=False,row_tile=16,warps=4,split_k=1,*,packed_input=False):
        name=f'pairload-{self.magnitude_bits}-{width}-{int(has_bias)}-m{row_tile}-w{warps}-s{split_k}-p{int(packed_input)}'
        if name not in self._functions:
            source=original._SOURCE
            old='''        #pragma unroll
        for(int i=0;i<4;++i) {
          int k=start+thread*4+word*16+i;
          int q=(n<outputs && k<WIDTH) ? quant_half(w[(size_t)n*WIDTH+k],exponent) : 0;
          pack_digits(packed,q,i);
        }'''
            new='''        #pragma unroll
        for(int pair=0;pair<2;++pair) {
          int k=start+thread*4+word*16+pair*2;
          unsigned halves=0;
          if(n<outputs) {
            if((WIDTH%2)==0 && (((unsigned long long)w)&3ull)==0ull && k+1<WIDTH)
              halves=*((const unsigned*)(w+(size_t)n*WIDTH+k));
            else {
              if(k<WIDTH) halves=(unsigned)w[(size_t)n*WIDTH+k];
              if(k+1<WIDTH) halves|=((unsigned)w[(size_t)n*WIDTH+k+1])<<16;
            }
          }
          pack_digits(packed,quant_half((u16)halves,exponent),pair*2);
          pack_digits(packed,quant_half((u16)(halves>>16),exponent),pair*2+1);
        }'''
            assert source.count(old)==1
            source=source.replace(old,new)
            defines=dict(WIDTH=width,MAGNITUDE_BITS=self.magnitude_bits,DIGITS=2 if self.magnitude_bits==14 else 3,
                         HAS_BIAS=int(has_bias),M_GROUPS=row_tile//16,WARPS=warps,SPLIT_K=split_k,PACKED_INPUT=int(packed_input))
            header=''.join(f'#define {k} {v}\n' for k,v in defines.items())
            self._functions[name]=self._compile(name,header+source,
                ['integer_input','integer_weights','integer_linear','integer_simt','integer_finish'],integer_mma=True)
        return self._functions[name]
