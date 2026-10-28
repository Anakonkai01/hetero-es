"""Unselected gate/up S1 projection: publish exact FP32 values instead of split int64 partials."""
from dataclasses import replace
import torch
from heteroes.eval import integer_cuda as ic,strict_cuda as sc

def source():
    start=ic._DECODE_FINISH_SOURCE.index('extern "C" __global__ void finish_silu(')
    end=ic._DECODE_FINISH_SOURCE.index('// quantize_input',start)
    body=ic._DECODE_FINISH_SOURCE[start:end]
    body=body[body.index('  const int k = '):]
    old='      float gate = projected(partials, rows, 2 * n, row, k, ex[row] + e0[k] - 2 * (MAGNITUDE_BITS - 1), b0, k, error);'
    assert body.count(old)==1
    body=body.replace(old,'      float gate = gate_input[(size_t)row*n+k];')
    old='      float up = projected(partials, rows, 2 * n, row, n + k, ex[row] + e1[k] - 2 * (MAGNITUDE_BITS - 1), b1, k, error);'
    assert body.count(old)==1
    body=body.replace(old,'      float up = up_input[(size_t)row*n+k];')
    header=''.join(f'#define {k} 0x{v:08x}u\n' for k,v in sc.reference_constants().items())
    return header+sc._OPS_SOURCE+r'''
__device__ __forceinline__ float loaded(float v,unsigned& bad){v=flush(v);note(v,bad);return v;}
extern "C" __global__ void float_pair_silu(const float* gate_input,const float* up_input,float* gated,
  unsigned* maxima,int* error,int rows,int n) {
'''+body

class TrafficKernels(ic.IntegerCudaKernels):
    def _decode_plan(self,*args,**kwargs):
        p=super()._decode_plan(*args,**kwargs)
        return replace(p,split_k=1,partial_bytes=0) if getattr(self,'_traffic_force_s1',False) else p
    @torch.inference_mode()
    def gate_up_silu_quantized(self,prepared,gate,up,biases=None,*,error_flag=None,decode_target_ctas_per_sm=None):
        rows,width=prepared[1].numel(),gate.shape[1]
        if not (self.arch=='sm_120' and self.magnitude_bits==22 and 16<rows<=128 and width%16==0
                and gate.shape==up.shape and decode_target_ctas_per_sm==8):
            return super().gate_up_silu_quantized(prepared,gate,up,biases,error_flag=error_flag,decode_target_ctas_per_sm=decode_target_ctas_per_sm)
        biases=(None,None) if biases is None else biases
        value=self._prepared_shape(prepared,gate)
        for w,b in zip((gate,up),biases):sc.validate_linear(value,w,b,device=self.device)
        flag=self.new_error_flag() if error_flag is None else error_flag
        n=gate.shape[0];maxima=torch.empty(rows,dtype=torch.int32,device=self.device)
        self._traffic_force_s1=True
        try:
            a,b=self._linear_group(value,rows,width,(gate,up),biases,prepared,flag,decode_target_ctas_per_sm,maxima=maxima)
        finally:self._traffic_force_s1=False
        name='float-pair-silu-traffic-v1'
        if name not in self._functions:
            self._functions[name]=self._compile(name,source(),['float_pair_silu'],ptx_exact=sc.OPS_PTX_EXACT,sass_exact=sc.OPS_SASS_EXACT)['float_pair_silu']
        gated=torch.empty((rows,n),device=self.device)
        self._launch(self._functions[name],grid=(-(-n//256),rows),block=(256,1),pointers=(a,b,gated,maxima,flag),integers=(rows,n))
        planes,exponents=self._planes(rows,n)
        self._launch(self._finish_functions(1,False)['pack_rows'],grid=(-(-((n+3)//4)//256),rows),block=(256,1),
                     pointers=(gated,maxima,planes,exponents),integers=(rows,n))
        self._finish(flag,error_flag)
        return planes,exponents
