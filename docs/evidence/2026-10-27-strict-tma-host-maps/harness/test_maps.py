"""Patching shared host descriptor templates must bind each launch/capture node to its own live tensors."""
import torch
from heteroes.eval.integer_cuda import IntegerCudaKernels
from tma_byvalue import TmaByValue
from host_maps import HostMapCache

def test_two_captured_launches_reusing_cpu_template_keep_independent_bindings():
    c=TmaByValue(80,64,1,2,3);k=c.k;cache=HostMapCache(k,capacity=4)
    g=torch.Generator(device='cuda').manual_seed(496)
    xs=[torch.randn(33,80,device='cuda',generator=g) for _ in range(2)]
    ws=[(torch.randn(35,80,device='cuda',generator=g)*.03).half() for _ in range(2)]
    flags=[k.new_error_flag() for _ in range(2)]
    prepared=[k.quantize_input(x,_packed=True,error_flag=f) for x,f in zip(xs,flags)]
    ew=[k._weight_exponents(w,f) for w,f in zip(ws,flags)]
    outputs=[];addresses=[]
    for p,w,e,f in zip(prepared,ws,ew,flags):
        maps=cache.maps(w,p[0],33,80,64);addresses.append(tuple(a.ctypes.data for a in maps))
        outputs.append(c.project(p,w,e,f,descriptors=maps))
    assert addresses[0]==addresses[1] and len(cache.entries)==2
    graph=torch.cuda.CUDAGraph()
    with torch.cuda.graph(graph):
        captured=[c.project(p,w,e,f,descriptors=cache.maps(w,p[0],33,80,64)) for p,w,e,f in zip(prepared,ws,ew,flags)]
    for sign in (1.,-1.):
        ws[0].mul_(sign);ws[1].mul_(sign)
        for e,w,f in zip(ew,ws,flags):e.copy_(k._weight_exponents(w,f))
        graph.replay()
        for i in range(2):
            expected=k._linear(xs[i],ws[i],error_flag=flags[i])
            assert flags[i].item()==0
            assert torch.equal(expected.view(torch.int32),captured[i].view(torch.int32))

def test_host_template_cache_stays_bounded_across_layout_changes():
    torch.empty(1,device='cuda');k=IntegerCudaKernels('cuda',magnitude_bits=22);cache=HostMapCache(k,capacity=2)
    for rows in (17,33,65,17):
        w=torch.ones(35,80,device='cuda',dtype=torch.float16)
        planes=k.quantize_input(torch.ones(rows,80,device='cuda'),_packed=True)[0]
        a,b=cache.maps(w,planes,rows,80,64)
        assert a.size==b.size==128 and len(cache.entries)<=2
