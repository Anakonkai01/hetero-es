"""Unselected B13/radix128 product decomposition, with original FP16 weights and bounded scratch."""
import hashlib
from pathlib import Path
import torch
from heteroes.canonical import canonical_json_hash
from heteroes.eval import integer_cuda as ic,strict_cuda as sc

def once(source,old,new):
    if source.count(old)!=1:raise ValueError('Prototype parent source anchor changed')
    return source.replace(old,new)

def source_for(method):
    source=ic._SOURCE
    start=source.index('__device__ __forceinline__ void pack_digits(')
    end=source.index('\n#if WEIGHT_PREFETCH',start)
    source=source[:start]+r'''
__device__ __forceinline__ unsigned add_bytes(unsigned a,unsigned b) {
  return ((a&0x7f7f7f7fu)+(b&0x7f7f7f7fu))^((a^b)&0x80808080u);
}
__device__ __forceinline__ void pack_digits(unsigned* words,int q,int element) {
  int low=((q+64)&127)-64;
  int high=(q-low)/128;
  words[0]|=((unsigned)low&255u)<<(8*element);
  words[1]|=((unsigned)high&255u)<<(8*element);
}
'''+source[end:]
    source=once(source,'int accum[M_GROUPS][2*DIGITS-1][4]={};','int accum[M_GROUPS][3][4]={};')
    old='''        #pragma unroll
        for(int i=0;i<DIGITS;++i) {
          #pragma unroll
          for(int j=0;j<DIGITS;++j) mma(accum[m][i+j],a[i],b[j]);
        }'''
    if method=='karatsuba':
        source=once(source,'''      #pragma unroll
      for(int m=0;m<M_GROUPS;++m) {''','''      unsigned bsum[2]={add_bytes(b[0][0],b[1][0]),add_bytes(b[0][1],b[1][1])};
      #pragma unroll
      for(int m=0;m<M_GROUPS;++m) {''')
        new='''        mma(accum[m][0],a[0],b[0]);
        mma(accum[m][2],a[1],b[1]);
        #pragma unroll
        for(int word=0;word<4;++word)a[0][word]=add_bytes(a[0][word],a[1][word]);
        mma(accum[m][1],a[0],bsum);'''
        reconstruct='''          i64 low=accum[m][0][d],high=accum[m][2][d];
          i64 middle=(i64)accum[m][1][d]-low-high;
          i64 sum=low+middle*128ll+high*16384ll;'''
    elif method=='schoolbook':
        new='''        mma(accum[m][0],a[0],b[0]);
        mma(accum[m][1],a[0],b[1]);
        mma(accum[m][1],a[1],b[0]);
        mma(accum[m][2],a[1],b[1]);'''
        reconstruct='''          i64 sum=(i64)accum[m][0][d]+128ll*(i64)accum[m][1][d]+16384ll*(i64)accum[m][2][d];'''
    else:raise ValueError('Unknown B13 product method')
    source=once(source,old,new)
    old='''          i64 sum=0;
          #pragma unroll
          for(int degree=0;degree<2*DIGITS-1;++degree) sum+=(i64)accum[m][degree][d]*(1ll<<(8*degree));'''
    return once(source,old,reconstruct)

class KaratsubaKernels(ic.IntegerCudaKernels):
    def __init__(self,device,*,method='karatsuba',max_partial_bytes=16*1024**2):
        if method not in ('karatsuba','schoolbook'):raise ValueError('Unknown B13 product method')
        super().__init__(device,magnitude_bits=22,max_partial_bytes=max_partial_bytes,weight_load='prefetch2')
        self.magnitude_bits=13;self.method=method;self.source=source_for(method)

    def _integer_functions(self,width,has_bias=False,row_tile=16,warps=4,split_k=1,*,packed_input=False):
        name=f'b13-{self.method}-k{width}-bias{int(has_bias)}-m{row_tile}-w{warps}-s{split_k}-p{int(packed_input)}'
        if name not in self._functions:
            header=''.join(f'#define {key} {value}\n'for key,value in dict(
                WIDTH=width,MAGNITUDE_BITS=13,DIGITS=2,HAS_BIAS=int(has_bias),M_GROUPS=row_tile//16,
                WARPS=warps,SPLIT_K=split_k,PACKED_INPUT=int(packed_input),WEIGHT_READ32=0,WEIGHT_PREFETCH=1).items())
            self._functions[name]=self._compile(name,header+self.source,
                ['integer_input','integer_weights','integer_linear','integer_simt','integer_finish'],integer_mma=True)
        return self._functions[name]

    @torch.inference_mode()
    def quantize_input(self,value,*,error_flag=None,_functions=None,_packed=False):
        if not _packed:return super().quantize_input(value,error_flag=error_flag,_functions=_functions,_packed=False)
        if value.ndim!=2 or not 1<=value.shape[1]<=32768:raise ValueError('Invalid packed B13 input')
        (value,)=self._float32(value)
        functions=self._integer_functions(value.shape[1],packed_input=True)if _functions is None else _functions
        quantized=torch.empty((2,value.shape[0],(value.shape[1]+3)//4),dtype=torch.int32,device=self.device)
        exponents=torch.empty(value.shape[0],dtype=torch.int32,device=self.device)
        flag=self.new_error_flag()if error_flag is None else error_flag
        self._launch(functions['integer_input'],grid=value.shape[0],block=(256,1),
                     pointers=(value,quantized,exponents,flag),integers=(value.shape[0],))
        self._finish(flag,error_flag)
        return quantized,exponents

    def identity(self):
        result={**sc.StrictCudaKernels.identity(self),'kernel':'row_scaled_b13_radix128_products_probe',
                'arithmetic':{'magnitudeBits':13,'scale':'2^(floor_log2(row_absmax)-12)',
                              'dot':'exact_int64_then_scaled_rne_signed_ftz','bias':'strict_f32_add_rn_signed_ftz'},
                'productImplementation':self.method,'weight':'one_live_fp16_set',
                'packing':'low_high_two_signed_byte_planes_sum_in_registers','maxPartialBytes':self.max_partial_bytes,
                'parentIntegerSourceSha256':hashlib.sha256(Path(ic.__file__).read_bytes()).hexdigest(),
                'prototypeSourceSha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                'hardwareQualified':False}
        result['fingerprint']=canonical_json_hash({k:v for k,v in result.items()if k!='fingerprint'})
        return result
