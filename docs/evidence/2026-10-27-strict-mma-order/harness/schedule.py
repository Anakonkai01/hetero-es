"""Same nine signed-byte products and five degree accumulators; spread dependent IMMA destinations."""
from heteroes.eval.integer_cuda import IntegerCudaKernels

OLD='''          #pragma unroll
          for(int i=0;i<DIGITS;++i) {
            #pragma unroll
            for(int jd=0;jd<DIGITS;++jd) {
              #pragma unroll
              for(int j=0;j<JN;++j) mma(accum[m][j][i+jd],a[i],b[j][jd]);
            }
          }'''
PAIRS=((0,2),(0,1),(1,2),(1,1),(0,0),(1,0),(2,0),(2,1),(2,2))

def transform(s):
    assert s.count(OLD)==1
    assert sorted(PAIRS)==[(i,j) for i in range(3) for j in range(3)]
    new='\n'.join(f'          #pragma unroll\n          for(int j=0;j<JN;++j) mma(accum[m][j][{i+d}],a[{i}],b[j][{d}]);' for i,d in PAIRS)
    return s.replace(OLD,new)

class ScheduledKernels(IntegerCudaKernels):
    def _compile(self,name,source,entries,**kwargs):
        if self.magnitude_bits==22 and OLD in source:
            source=transform(source);name='balanced-mma-v1-'+name
        return super()._compile(name,source,entries,**kwargs)
