"""Lossless integer chord prediction plus nibble residuals; no numerical approximation is published."""
import numpy as np
SHIFT=11

def prediction(mantissas,anchors):
    index=mantissas>>SHIFT
    low=(mantissas&((1<<SHIFT)-1)).astype(np.int64)
    start=anchors[index].astype(np.int64)
    delta=anchors[index+1].astype(np.int64)-start
    return start+((delta*low)>>SHIFT)

def compress(table):
    anchors=np.concatenate([table[::1<<SHIFT],np.array([int(table[0])-(1<<23)],np.uint32)])
    mantissas=np.arange(1<<23,dtype=np.uint32)
    residual=table.astype(np.int64)-prediction(mantissas,anchors)
    assert residual.min()>=-8 and residual.max()<=7
    code=(residual+8).astype(np.uint8)
    packed=code[::2]|(code[1::2]<<4)
    assert np.array_equal(unpack(mantissas,anchors,packed),table)
    return anchors,packed

def unpack(mantissas,anchors,packed):
    code=((packed[mantissas>>1]>>((mantissas&1)*4))&15).astype(np.int64)-8
    return (prediction(mantissas,anchors)+code).astype(np.uint32)
