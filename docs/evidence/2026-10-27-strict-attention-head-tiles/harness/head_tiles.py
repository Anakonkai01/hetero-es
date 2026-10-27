"""Unselected GQA scheduling: split repeat heads over CTAs without changing a live head's arithmetic."""
from heteroes.eval import strict_cuda as sc
from heteroes.eval.integer_cuda import IntegerCudaKernels

def once(s,old,new):
    assert s.count(old)==1,(old,s.count(old))
    return s.replace(old,new)

def source():
    start=sc._OPS_SOURCE.index('extern "C" __global__ void __launch_bounds__(512) strict_attention_gqa(')
    prefix,body=sc._OPS_SOURCE[:start],sc._OPS_SOURCE[start:]
    body=once(body,'strict_attention_gqa(','head_tile_attention(')
    body=once(body,'const int tid = r * dim + x, threads = repeats * dim, h = kv * repeats + r;',
              'const int tile_heads=(int)blockDim.y, tid=r*dim+x, threads=tile_heads*dim;\n  const int h=kv*repeats+blockIdx.z*tile_heads+r;\n  const bool head_live=blockIdx.z*tile_heads+r<repeats;')
    body=body.replace('query + repeats * padded','query + tile_heads * padded').replace('numerators + repeats * keys','numerators + tile_heads * keys')
    body=once(body,'query[r * padded + x + (x >> 5)] = load(q + ((size_t)h * length + i) * dim + x, bad);',
              'query[r*padded+x+(x>>5)]=head_live ? load(q+((size_t)h*length+i)*dim+x,bad) : 0.0f;')
    body=once(body,'const bool live = score_row < rows;','const bool live = score_row < rows && blockIdx.z*tile_heads+score_head<repeats;')
    # Dead head lanes still participate in K/V staging and CTA barriers. Their synthetic zero scores
    # produce a finite unit softmax; their value arithmetic and output stores are omitted.
    body=once(body,'if (live && lane == 0) numerators[score_head * keys + first + score_row]',
              'if (score_row < rows && lane == 0) numerators[score_head * keys + first + score_row]')
    begin=body.index('    float group[4];',body.index('  Tree t;'))
    end=body.index('    push(t, group[0], bad);',begin)+len('    push(t, group[0], bad);')
    body=body[:begin]+'    if(head_live) {\n'+body[begin:end]+'\n    }'+body[end:]
    body=once(body,'  out[(size_t)i * heads * dim + h * dim + x] = finish(t, bad);',
              '  if(head_live)out[(size_t)i*heads*dim+h*dim+x]=finish(t,bad);')
    header=''.join(f'#define {n} 0x{v:08x}u\n' for n,v in sc.reference_constants().items())
    return header+prefix+body

class HeadTileKernels(IntegerCudaKernels):
    head_tile=4
    def __init__(self,*args,head_tile=4,**kwargs):
        assert head_tile in (2,4)
        super().__init__(*args,**kwargs);self.head_tile=head_tile
    def _launch_attention(self,grid,pointers,integers,scale,max_keys):
        repeats,dim=integers[4:6];tile=self.head_tile
        shared=4*((tile+32)*(dim+max(1,dim//32))+2*tile*max_keys)
        if not (repeats>tile and sc.gqa_attention_eligible(dim,tile,shared)
                and self._attention_entry in ('strict_attention_gqa','strict_attention_prefill')):
            return super()._launch_attention(grid,pointers,integers,scale,max_keys)
        name='gqa-head-tiles-v1'
        if name not in self._functions:
            self._functions[name]=self._compile(name,source(),['head_tile_attention'],ptx_exact=sc.OPS_PTX_EXACT,sass_exact=sc.OPS_SASS_EXACT)['head_tile_attention']
        self._launch(self._functions[name],grid=(*grid[:2],-(-repeats//tile)),block=(dim,tile),pointers=pointers,
                     integers=integers,floats=(scale,),shared=shared)
