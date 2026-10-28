"""Unselected vendor batched GEMM on bounded integer coefficients; two fixed scratch allocations."""
import hashlib
from pathlib import Path

import torch

from heteroes.canonical import canonical_json_hash
from heteroes.eval import integer_cuda as ic,strict_cuda as sc
from heteroes.eval.reference_ops import ReferenceArithmeticError
from bounded_cuda import _MMA
from half2_cuda import Half2BoundedKernels,_PAIR

_AUX=r'''
extern "C" __global__ void vendor_weights(const u16* source,u16* target,const int* exponents,int outputs) {
  int n=blockIdx.y,k=(blockIdx.x*256+threadIdx.x)*2;
  if(n>=outputs || k>=WIDTH)return;
  unsigned raw;
  const u16* pointer=source+(size_t)n*WIDTH+k;
  if((((unsigned long long)pointer)&3ull)==0ull)
    asm volatile("ld.global.u32 %0, [%1];" : "=r"(raw) : "l"(pointer));
  else raw=(unsigned)pointer[0]|((unsigned)pointer[1]<<16);
  ((unsigned*)target)[((size_t)n*WIDTH+k)/2]=quant_half_pair(raw,exponents[n]);
}
extern "C" __global__ void vendor_finish(const float* partials,const u16* bias,const int* ex,const int* ew,
                                         float* output,int* error,int rows,int outputs,int batches) {
  int n=blockIdx.x*256+threadIdx.x,row=blockIdx.y;
  if(n>=outputs)return;
  i64 sum=0;
  for(int b=0;b<batches;++b) {
    float p=partials[((size_t)b*rows+row)*outputs+n];
    if((__float_as_uint(p)&0x7fffffffu)>0x4b800000u){atomicOr(error,1);p=0.0f;}
    int integer;float back;
    asm("cvt.rzi.s32.f32 %0, %1;" : "=r"(integer) : "f"(p));
    asm("cvt.rn.f32.s32 %0, %1;" : "=f"(back) : "r"(integer));
    if(p!=back)atomicOr(error,1);
    sum+=(i64)integer;
  }
  float value=encode(sum,ex[row]+ew[n]-(MAGNITUDE_BITS-1)-(WEIGHT_BITS-1),error);
  if(HAS_BIAS)value=add_rn(value,widen(bias[n]));
  output[(size_t)row*outputs+n]=value;
  if((__float_as_uint(value)&0x7f800000u)==0x7f800000u)atomicOr(error,1);
}
'''


class VendorBoundedKernels(Half2BoundedKernels):
    def __init__(self,*args,max_quantized_bytes=32*1024**2,**kwargs):
        super().__init__(*args,**kwargs)
        if type(max_quantized_bytes)is not int or max_quantized_bytes<2:raise ValueError('Quantized tile budget')
        self.max_quantized_bytes=max_quantized_bytes
        self._weight_scratch=torch.zeros(max_quantized_bytes//2,dtype=torch.float16,device=self.device)
        self._partial_scratch=torch.zeros(self.max_partial_bytes//4,dtype=torch.float32,device=self.device)
        self._scratch_stream=None
        self.vendor_calls=0

    @staticmethod
    def _check_fp32():
        if torch.backends.cuda.matmul.allow_fp16_reduced_precision_reduction or torch.backends.cuda.matmul.allow_fp16_accumulation:
            raise ReferenceArithmeticError('Bounded vendor GEMM requires FP32 accumulation without reduced precision')

    def operator_workspaces(self):return (self._weight_scratch,self._partial_scratch)

    def _begin_request(self,weights):
        self._check_fp32()
        super()._begin_request(weights)
        self._scratch_stream=torch.cuda.current_stream(self.device)

    def _end_request(self):
        for buffer in self.operator_workspaces():buffer.zero_()
        super()._end_request()
        self._scratch_stream=None

    def _vendor_functions(self,width,has_bias):
        name=f'vendor-aux-a{self.activation_bits}-w{self.weight_bits}-k{width}-bias{int(has_bias)}'
        if name not in self._functions:
            source=ic._SOURCE
            prefix=source[:source.index('__device__ __forceinline__ void pack_digits(')]
            start=prefix.index('__device__ __forceinline__ int quant_half(')
            prefix=prefix[:start]+prefix[start:].replace('MAGNITUDE_BITS','WEIGHT_BITS')
            encoder=source[source.index('__device__ __forceinline__ u64 rne64('):source.index('__device__ __forceinline__ void mma(')]
            header=f'#define WIDTH {width}\n#define MAGNITUDE_BITS {self.activation_bits}\n#define WEIGHT_BITS {self.weight_bits}\n#define HAS_BIAS {int(has_bias)}\n'
            self._functions[name]=sc.StrictCudaKernels._compile(self,name,header+prefix+encoder+_MMA+_PAIR+_AUX,
                ['vendor_weights','vendor_finish'],
                ptx_exact=('cvt.rni.s32.f32','cvt.rzi.s32.f32','cvt.rn.f32.s32','cvt.rn.f16.s32',
                           'mul.rn.f16x2','add.rn.f16x2','sub.rn.f16x2'),
                sass_exact=('F2I.NTZ','F2I.TRUNC.NTZ','I2F','I2F.F16','I2FP.F16.S32','HMUL2','HADD2'))
        return self._functions[name]

    @torch.inference_mode()
    def _linear(self,value,weight,bias=None,*,error_flag=None,prepared=None,**kwargs):
        rows,width,outputs=sc.validate_linear(value,weight,bias,device=self.device)
        block=min(width&-width,self.block_k)
        batches=width//block
        if not self._request_active or rows>128 or block<16 or outputs>65535 or \
           outputs*width*2>self.max_quantized_bytes or batches*rows*outputs*4>self.max_partial_bytes:
            return super()._linear(value,weight,bias,error_flag=error_flag,prepared=prepared,**kwargs)
        self._check_fp32()
        if torch.cuda.current_stream(self.device)!=self._scratch_stream:
            raise ReferenceArithmeticError('Bounded vendor workspace belongs to another stream')
        flag=self.new_error_flag()if error_flag is None else error_flag
        encoded,ex=self.quantize_input(value.reshape(rows,width),error_flag=flag)if prepared is None else prepared
        ew=self._weight_exponents(weight,flag)
        functions=self._vendor_functions(width,bias is not None)
        quantized=self._weight_scratch[:outputs*width].view(outputs,width)
        partials=self._partial_scratch[:batches*rows*outputs].view(batches,rows,outputs)
        self._launch(functions['vendor_weights'],grid=((width//2+255)//256,outputs,1),block=(256,1),
                     pointers=(weight,quantized,ew),integers=(outputs,))
        left=encoded.view(rows,batches,block).permute(1,0,2)
        right=quantized.view(outputs,batches,block).permute(1,2,0)
        torch.bmm(left,right,out_dtype=torch.float32,out=partials)
        out=torch.empty((rows,outputs),device=self.device,dtype=torch.float32)
        self._launch(functions['vendor_finish'],grid=((outputs+255)//256,rows,1),block=(256,1),
                     pointers=(partials,weight if bias is None else bias,ex,ew,out,flag),integers=(rows,outputs,batches))
        self.vendor_calls+=1
        self._finish(flag,error_flag)
        return out.reshape(*value.shape[:-1],outputs)

    def identity(self):
        result={**super().identity(),'gemm':'torch.bmm_fp16_to_fp32_bounded_integer_partials_probe',
                'torch':torch.__version__,'maxQuantizedBytes':self.max_quantized_bytes,
                'maxVendorPartialBytes':self.max_partial_bytes,'vendorCallsOutsideReplay':self.vendor_calls,
                'vendorSourceSha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                'allowFP16ReducedPrecisionReduction':torch.backends.cuda.matmul.allow_fp16_reduced_precision_reduction,
                'allowFP16Accumulation':torch.backends.cuda.matmul.allow_fp16_accumulation}
        result['fingerprint']=canonical_json_hash({k:v for k,v in result.items()if k!='fingerprint'})
        return result
