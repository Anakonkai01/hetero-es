"""Scratch independent Fraction quantizer and integer-dot oracle for asymmetric precision."""
from fractions import Fraction

import torch

from heteroes.eval.integer_reference import scaled_integer_bits
from heteroes.eval import reference_ops


def round_even(value):
    whole,remainder=divmod(value.numerator,value.denominator)
    return whole+int(2*remainder>value.denominator or (2*remainder==value.denominator and whole%2))


def quantize_rows(value,bits):
    assert value.dtype==torch.float32 and value.device.type=='cpu' and value.ndim==2
    assert bits in (6,14,22) and torch.isfinite(value).all()
    integers=[];exponents=[]
    for row in value:
        numbers=[0.0 if abs(float(v))<2**-126 else float(v) for v in row]
        maximum=max(map(abs,numbers))
        if maximum:
            exponent=Fraction(maximum).numerator.bit_length()-Fraction(maximum).denominator.bit_length()
        else:exponent=0
        scale=Fraction(2)**(exponent-(bits-1))
        quantized=[round_even(Fraction(v)/scale) for v in numbers]
        assert max(map(abs,quantized))<=2**bits
        integers.append(quantized);exponents.append(exponent)
    return torch.tensor(integers,dtype=torch.int64),torch.tensor(exponents,dtype=torch.int64)


def linear(value,weight,bias=None,*,activation_bits,weight_bits):
    qx,ex=quantize_rows(value,activation_bits)
    qw,ew=quantize_rows(weight.float(),weight_bits)
    sums=qx@qw.T
    scale=ex[:,None]+ew[None,:]-(activation_bits-1)-(weight_bits-1)
    encoded=[]
    for integers,scales in zip(sums.tolist(),scale.tolist(),strict=True):
        row=[scaled_integer_bits(s,e) for s,e in zip(integers,scales,strict=True)]
        encoded.append([u if u<2**31 else u-2**32 for u in row])
    out=torch.tensor(encoded,dtype=torch.int32).view(torch.float32)
    if bias is not None:out=reference_ops.add(out,bias.float())
    return out
