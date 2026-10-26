"""Independent rational oracle: fixed 256-term serial IEEE FP32 FMA chunks, then pruned FTZ tree."""
from fractions import Fraction
import math
import struct

import torch

from heteroes.eval.reference_ops import ReferenceArithmeticError

CHUNK=256


def bits(value):return struct.unpack('<I',struct.pack('<f',float(value)))[0]
def value(word):return struct.unpack('<f',struct.pack('<I',word))[0]


def rounded_div(n,d):
    q,r=divmod(n,d)
    return q+int(2*r>d or(2*r==d and(q&1)))


def encode(exact,negative_zero=False):
    if not exact:return 0x80000000 if negative_zero else 0
    sign=0x80000000 if exact<0 else 0
    n,d=abs(exact.numerator),exact.denominator
    exponent=n.bit_length()-d.bit_length()
    if (n<(d<<exponent))if exponent>=0 else ((n<<-exponent)<d):exponent-=1
    if exponent < -126:
        significand=rounded_div(n<<149,d)
        return sign|significand
    shift=23-exponent
    significand=rounded_div(n<<shift,d)if shift>=0 else rounded_div(n,d<<-shift)
    if significand>=1<<24:significand>>=1;exponent+=1
    if exponent>127:raise ReferenceArithmeticError('Nonfinite ordered FMA arithmetic')
    return sign|((exponent+127)<<23)|(significand&0x7fffff)


def flush(x):
    word=bits(x)
    return value(word&0x80000000)if(word&0x7fffffff)<0x00800000 else x


def fma(a,b,c):
    exact=Fraction(a)*Fraction(b)+Fraction(c)
    negative=not a*b and not c and bool((bits(a)^bits(b))&bits(c)&0x80000000)
    return value(encode(exact,negative))


def add(a,b):
    negative=not a and not b and bool(bits(a)&bits(b)&0x80000000)
    return flush(value(encode(Fraction(a)+Fraction(b),negative)))


def linear(x,w,bias=None):
    if x.device.type!='cpu' or w.device.type!='cpu' or x.dtype!=torch.float32 or w.dtype!=torch.float16:
        raise ReferenceArithmeticError('Ordered FMA oracle requires CPU FP32 inputs and FP16 weights')
    if not torch.isfinite(x).all()or not torch.isfinite(w).all()or(bias is not None and not torch.isfinite(bias).all()):
        raise ReferenceArithmeticError('Nonfinite ordered FMA input')
    inputs=[[flush(v)for v in row]for row in x.tolist()]
    weights=w.float().tolist()
    result=[]
    for row in inputs:
        outputs=[]
        for n,weight in enumerate(weights):
            partial=[]
            for first in range(0,len(row),CHUNK):
                accumulator=0.0
                for a,b in zip(row[first:first+CHUNK],weight[first:first+CHUNK],strict=True):
                    accumulator=fma(a,b,accumulator)
                partial.append(flush(accumulator))
            while len(partial)>1:
                partial=[add(partial[i],partial[i+1])if i+1<len(partial)else partial[i]for i in range(0,len(partial),2)]
            output=partial[0]
            if bias is not None:output=add(output,float(bias[n]))
            outputs.append(flush(output))
        result.append(outputs)
    return torch.tensor(result,dtype=torch.float32)
