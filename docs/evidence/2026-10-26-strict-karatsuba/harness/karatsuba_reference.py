"""Independent rational oracle for NEW row-scaled B13 arithmetic; exact radix-independent int dot."""
from fractions import Fraction
import math
import torch
from heteroes.eval import integer_reference as ir,reference_ops as ops
from heteroes.eval.reference_ops import ReferenceArithmeticError

def digits(q):
    if type(q)is not int or not -8192<=q<=8192:raise ValueError('Outside B13 bound')
    low=(q+64)%128-64
    high=(q-low)//128
    return low,high,low+high

def quantize(matrix):
    if matrix.device.type!='cpu' or matrix.dtype!=torch.float32 or matrix.ndim!=2:
        raise ReferenceArithmeticError('CPU FP32 oracle matrix required')
    if not torch.isfinite(matrix).all():raise ReferenceArithmeticError('Nonfinite B13 input')
    rows=[];exponents=[]
    for row in matrix.tolist():
        row=[v if abs(v)>=2.**-126 else 0. for v in row]
        maximum=max(map(abs,row));exponent=math.frexp(maximum)[1]-1 if maximum else 0
        scale=Fraction(2)**(exponent-12)
        rows.append([round(Fraction(v)/scale)for v in row]);exponents.append(exponent)
    return rows,exponents

def linear(x,w,bias=None):
    if x.device.type!='cpu' or w.device.type!='cpu' or x.dtype!=torch.float32 or w.dtype!=torch.float16:
        raise ReferenceArithmeticError('CPU FP32 input and FP16 weight required')
    qx,ex=quantize(x);qw,ew=quantize(w.float())
    result=[]
    for row,e in zip(qx,ex,strict=True):
        encoded=[]
        for weight,f in zip(qw,ew,strict=True):
            integer=sum(a*b for a,b in zip(row,weight,strict=True))
            bits=ir.scaled_integer_bits(integer,e+f-24)
            encoded.append(bits if bits<2**31 else bits-2**32)
        result.append(encoded)
    output=torch.tensor(result,dtype=torch.int32).view(torch.float32)
    return output if bias is None else ops.add(output,bias.float())
