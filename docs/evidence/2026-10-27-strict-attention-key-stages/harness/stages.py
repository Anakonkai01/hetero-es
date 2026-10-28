"""Larger GQA K/V stages with the original thread count and ordered 32-key value subtrees."""
from heteroes.eval import strict_cuda as sc
from heteroes.eval.integer_cuda import IntegerCudaKernels

def once(s,old,new):
    assert s.count(old)==1,(old,s.count(old))
    return s.replace(old,new)

def source(tile):
    assert tile in (64,128)
    start=sc._OPS_SOURCE.index('extern "C" __global__ void __launch_bounds__(512) strict_attention_gqa(')
    prefix,body=sc._OPS_SOURCE[:start],sc._OPS_SOURCE[start:]
    body=once(body,'strict_attention_gqa(','key_stage_attention(')
    body=once(body,'tile + 32 * padded','tile + KEY_TILE * padded')
    body=body.replace('float4 staged[4]','float4 staged[LOADS]')
    body=body.replace('u < 4','u < LOADS')
    body=body.replace('keys - first < 32 ? keys - first : 32','keys - first < KEY_TILE ? keys - first : KEY_TILE')
    body=body.replace('first += 32','first += KEY_TILE')
    body=body.replace('first + 32 < keys','first + KEY_TILE < keys').replace('first + 32);','first + KEY_TILE);')
    begin=body.index('    const bool live = score_row < rows;')
    end=body.index('  }\n  fetch(values_base, 0);',begin)
    old=body[begin:end].replace('score_row','local_row')
    body=body[:begin]+'    #pragma unroll 1\n    for(int sub=0;sub<KEY_TILE;sub+=32) {\n      int local_row=score_row+sub;\n'+old+'    }\n'+body[end:]
    begin=body.index('    float group[4];',body.index('  Tree t;'))
    end=body.index('    push(t, group[0], bad);',begin)+len('    push(t, group[0], bad);')
    old=body[begin:end]
    old=old.replace('rows - base','subtree_rows - base').replace('(rows + 7)','(subtree_rows + 7)')
    old=old.replace('scores[first + base + item]','scores[first + sub + base + item]')
    old=old.replace('tile[(base + item) * padded','tile[(sub + base + item) * padded')
    body=body[:begin]+'    #pragma unroll 1\n    for(int sub=0;sub<rows;sub+=32) {\n      int subtree_rows=rows-sub<32 ? rows-sub : 32;\n'+old+'\n    }'+body[end:]
    header=''.join(f'#define {n} 0x{v:08x}u\n' for n,v in sc.reference_constants().items())
    return header+f'#define KEY_TILE {tile}\n#define LOADS {tile//16}\n'+prefix+body

class KeyStageKernels(IntegerCudaKernels):
    key_tile=64
    def __init__(self,*args,key_tile=64,**kwargs):
        assert key_tile in (64,128)
        super().__init__(*args,**kwargs);self.key_tile=key_tile
    def _launch_attention(self,grid,pointers,integers,scale,max_keys):
        repeats,dim=integers[4:6];tile=self.key_tile
        shared=4*((repeats+tile)*(dim+max(1,dim//32))+2*repeats*max_keys)
        if not (self.arch=='sm_120' and dim==64 and repeats>=4 and dim*repeats<=512
                and shared<=96*1024 and self._attention_entry in ('strict_attention_gqa','strict_attention_prefill')):
            return super()._launch_attention(grid,pointers,integers,scale,max_keys)
        name=f'gqa-key-stage-v1-k{tile}'
        if name not in self._functions:
            self._functions[name]=self._compile(name,source(tile),['key_stage_attention'],ptx_exact=sc.OPS_PTX_EXACT,sass_exact=sc.OPS_SASS_EXACT)['key_stage_attention']
        fn=self._functions[name]
        configured=getattr(self,'_stage_shared_config',{})
        if shared>48*1024 and shared>configured.get(name,0):
            sc._check(self._driver.cuFuncSetAttribute(fn,self._driver.CUfunction_attribute.CU_FUNC_ATTRIBUTE_MAX_DYNAMIC_SHARED_SIZE_BYTES,shared))
            configured[name]=shared;self._stage_shared_config=configured
        self._launch(fn,grid=grid[:2],block=(dim,repeats),pointers=pointers,integers=integers,floats=(scale,),shared=shared)
