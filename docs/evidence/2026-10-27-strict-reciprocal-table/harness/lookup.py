"""CPU-only unselected exact reciprocal table; no vendor reciprocal or altered Newton iteration."""
import numpy as np

def newton(bits):
    value=bits.view(np.float32)
    result=(np.uint32(0x7EF311C3)-bits).view(np.float32)
    for _ in range(5):
        product=np.multiply(value,result,dtype=np.float32)
        correction=np.subtract(np.float32(2),product,dtype=np.float32)
        result=np.multiply(result,correction,dtype=np.float32)
    return result.view(np.uint32)

def build_table():
    bits=np.arange(1<<23,dtype=np.uint32)|np.uint32(0x3F800000)
    return newton(bits)

def lookup(value,table):
    if value.dtype!=np.float32 or not np.all((value>=np.float32(1e-30))&(value<=np.float32(1e30))):
        raise ValueError('This probe only handles the admitted reciprocal domain')
    bits=value.view(np.uint32)
    exponent=(bits>>23).astype(np.int64)-127
    result=(table[bits&0x7FFFFF].astype(np.int64)-(exponent<<23)).astype(np.uint32)
    return result.view(np.float32)
