"""Every possible FP16 encoding, including signed zeros, infinities and NaN payloads, is copied as U16."""
import torch
from tma_copy_v3 import TmaCopy

def test_all_65536_u16_encodings_are_preserved():
    expected=torch.arange(65536,dtype=torch.int64).to(torch.int16).reshape(1024,64)
    values=expected.cuda();copy=TmaCopy()
    for y in range(0,1024,32):
        actual,flag=copy.run(values,0,y)
        assert int(flag.item())==0 and torch.equal(actual.cpu(),expected[y:y+32])
