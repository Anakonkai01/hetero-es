"""Unselected B14/B22 cooperative radix tiles: one packed A load per CTA and shared W conversion."""
import hashlib
from pathlib import Path

from heteroes.canonical import canonical_json_hash
from heteroes.eval import integer_cuda as ic

_TILE = r'''
__device__ __forceinline__ unsigned shared_address(const void* pointer) {
  unsigned long long address;
  asm volatile("cvta.to.shared.u64 %0, %1;" : "=l"(address) : "l"(pointer));
  return (unsigned)address;
}
__device__ __forceinline__ void load_a(unsigned* a,const void* pointer) {
  unsigned address=shared_address(pointer);
  asm volatile("ldmatrix.sync.aligned.m8n8.x4.shared.b16 {%0,%1,%2,%3}, [%4];"
    : "=r"(a[0]),"=r"(a[1]),"=r"(a[2]),"=r"(a[3]) : "r"(address));
}
__device__ __forceinline__ void load_b(unsigned* b,const void* pointer) {
  unsigned address=shared_address(pointer);
  asm volatile("ldmatrix.sync.aligned.m8n8.x2.shared.b16 {%0,%1}, [%2];"
    : "=r"(b[0]),"=r"(b[1]) : "r"(address));
}
__device__ __forceinline__ void copy_raw_tile(u16* target,const u16* weight,int column,int outputs,int start) {
  for(int copy=threadIdx.x;copy<N_TILE*(K_TILE/8);copy+=32*WARPS) {
    int n=copy/(K_TILE/8),local=(copy%(K_TILE/8))*8;
    int k=start+(local/32)*SPLIT_K*32+local%32;
    u16* destination=target+n*K_TILE+local;
#if WIDTH % 8 == 0
    if((((unsigned long long)weight)&15ull)==0ull) {
      int valid=(column+n<outputs && k+7<WIDTH) ? 16 : 0;
      const u16* source=valid ? weight+(size_t)(column+n)*WIDTH+k : weight;
      unsigned address=shared_address(destination);
      asm volatile("cp.async.ca.shared.global [%0], [%1], 16, %2;" ::
        "r"(address),"l"(source),"r"(valid) : "memory");
    } else
#endif
    {
      #pragma unroll
      for(int i=0;i<8;++i)
        destination[i]=(column+n<outputs && k+i<WIDTH) ? weight[(size_t)(column+n)*WIDTH+k+i] : 0;
    }
  }
}

extern "C" __global__ void __launch_bounds__(32*WARPS)
integer_linear(const qi_t* x,const u16* w,const u16* bias,const int* ex,const int* ew,
               float* out,int* error,i64* partials,int rows,int outputs) {
  int lane=threadIdx.x&31,warp=threadIdx.x>>5,warp_m=warp/4,warp_n=warp%4;
  int group=lane>>2,thread=lane&3,column=blockIdx.x*N_TILE;
  __shared__ __align__(16) u16 raw[2][N_TILE*K_TILE];
  __shared__ __align__(16) unsigned char a_shared[DIGITS][M_TILE][PITCH];
  __shared__ __align__(16) unsigned char b_shared[DIGITS][N_TILE][PITCH];
  for(int first=blockIdx.y*M_TILE;first<rows;first+=gridDim.y*M_TILE) {
    int accum[N_SUB][2*DIGITS-1][4]={};
    int phase=0;
    copy_raw_tile(raw[phase],w,column,outputs,blockIdx.z*32);
    asm volatile("cp.async.commit_group;" ::: "memory");
    for(int start=blockIdx.z*32;start<WIDTH;start+=SPLIT_K*K_TILE) {
      asm volatile("cp.async.wait_group 0;" ::: "memory");
      __syncthreads();
      copy_raw_tile(raw[phase^1],w,column,outputs,start+SPLIT_K*K_TILE);
      asm volatile("cp.async.commit_group;" ::: "memory");
      for(int word=threadIdx.x;word<N_TILE*(K_TILE/4);word+=32*WARPS) {
        int n=word/(K_TILE/4),local=(word%(K_TILE/4))*4;
        int exponent=column+n<outputs ? ew[column+n] : 0;
        unsigned packed[DIGITS]={};
        #pragma unroll
        for(int i=0;i<4;++i)pack_digits(packed,quant_half(raw[phase][n*K_TILE+local+i],exponent),i);
        #pragma unroll
        for(int d=0;d<DIGITS;++d)*(unsigned*)(&b_shared[d][n][local])=packed[d];
      }
      for(int word=threadIdx.x;word<DIGITS*M_TILE*(K_TILE/4);word+=32*WARPS) {
        int d=word/(M_TILE*(K_TILE/4)),local=word%(M_TILE*(K_TILE/4));
        int row=local/(K_TILE/4),kw=local%(K_TILE/4);
        int source=start/4+(kw/8)*SPLIT_K*8+kw%8;
        unsigned packed=(first+row<rows && source<(WIDTH+3)/4) ?
          ((const unsigned*)x)[((size_t)d*rows+first+row)*((WIDTH+3)/4)+source] : 0;
        *(unsigned*)(&a_shared[d][row][kw*4])=packed;
      }
      __syncthreads();
      #pragma unroll
      for(int chunk=0;chunk<K_TILE;chunk+=32) {
        unsigned a[DIGITS][4];
        #pragma unroll
        for(int d=0;d<DIGITS;++d)
          load_a(a[d],&a_shared[d][warp_m*16+(lane&15)][chunk+(lane>>4)*16]);
        #pragma unroll
        for(int sub=0;sub<N_SUB;++sub) {
          unsigned b[DIGITS][2];
          #pragma unroll
          for(int d=0;d<DIGITS;++d)
            load_b(b[d],&b_shared[d][warp_n*N_SUB*8+sub*8+(lane&7)][chunk+((lane>>3)&1)*16]);
          #pragma unroll
          for(int i=0;i<DIGITS;++i) {
            #pragma unroll
            for(int j=0;j<DIGITS;++j)mma(accum[sub][i+j],a[i],b[j]);
          }
        }
      }
      phase^=1;
    }
    asm volatile("cp.async.wait_group 0;" ::: "memory");
    __syncthreads();
    #pragma unroll
    for(int sub=0;sub<N_SUB;++sub) {
      #pragma unroll
      for(int d=0;d<4;++d) {
        int row=first+warp_m*16+group+(d>>1)*8;
        int n=column+warp_n*N_SUB*8+sub*8+thread*2+(d&1);
        if(row<rows && n<outputs) {
          i64 sum=0;
          #pragma unroll
          for(int degree=0;degree<2*DIGITS-1;++degree)sum+=(i64)accum[sub][degree][d]*(1ll<<(8*degree));
#if SPLIT_K > 1
          partials[((size_t)blockIdx.z*rows+row)*outputs+n]=sum;
#else
          float v=encode(sum,ex[row]+ew[n]-2*(MAGNITUDE_BITS-1),error);
          if(HAS_BIAS)v=add_rn(v,widen(bias[n]));
          out[(size_t)row*outputs+n]=v;
          if((__float_as_uint(v)&0x7f800000u)==0x7f800000u)atomicOr(error,1);
#endif
        }
      }
    }
  }
}

'''


class SharedTileKernels(ic.IntegerCudaKernels):
    def __init__(self,*args,nsub=1,k_tile=32,**kwargs):
        if nsub not in (1,2) or k_tile not in (32,64):raise ValueError('Prototype shared tile')
        self.nsub,self.k_tile=nsub,k_tile
        self._shared_launches={}
        super().__init__(*args,**kwargs)

    def _integer_functions(self,width,has_bias=False,row_tile=16,warps=4,split_k=1,*,packed_input=False):
        actual_warps=4*(row_tile//16)
        name=f'sharedtile-b{self.magnitude_bits}-k{width}-bias{int(has_bias)}-m{row_tile}-n{self.nsub*32}-kt{self.k_tile}-s{split_k}-p{int(packed_input)}'
        if name not in self._functions:
            source=ic._SOURCE
            start=source.index('extern "C" __global__ void __launch_bounds__(32*WARPS)\ninteger_linear')
            end=source.index('// Same arithmetic, different scheduling:',start)
            source=source[:start]+_TILE+source[end:]
            defines=dict(WIDTH=width,MAGNITUDE_BITS=self.magnitude_bits,DIGITS=2 if self.magnitude_bits==14 else 3,
                         HAS_BIAS=int(has_bias),M_GROUPS=row_tile//16,WARPS=actual_warps,SPLIT_K=split_k,
                         PACKED_INPUT=int(packed_input),WEIGHT_READ32=0,WEIGHT_PREFETCH=0,
                         M_TILE=row_tile,N_TILE=self.nsub*32,N_SUB=self.nsub,K_TILE=self.k_tile,PITCH=self.k_tile+16)
            header=''.join(f'#define {k} {v}\n'for k,v in defines.items())
            self._functions[name]=self._compile(name,header+source,
                ['integer_input','integer_weights','integer_linear','integer_simt','integer_finish'],integer_mma=True)
            self._shared_launches[id(self._functions[name]['integer_linear'])]=(actual_warps,self.nsub*32)
        return self._functions[name]

    def _launch(self,function,**kwargs):
        if id(function)in self._shared_launches:
            warps,columns=self._shared_launches[id(function)]
            rows,outputs=kwargs['integers']
            _,y,z=kwargs['grid']
            kwargs['grid']=((outputs+columns-1)//columns,y,z)
            kwargs['block']=(warps*32,1)
        return super()._launch(function,**kwargs)

    def identity(self):
        result={**super().identity(),'execution':'cooperative_shared_radix_ldmatrix_probe',
                'weightLoadEffective':'cta_raw_async_shared_radix_probe','nSub':self.nsub,'kTile':self.k_tile,
                'prototypeSourceSha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
        result['fingerprint']=canonical_json_hash({k:v for k,v in result.items()if k!='fingerprint'})
        return result
