from dataclasses import dataclass
from pathlib import Path
from types import MethodType
import torch
from heteroes.eval import strict_cuda as sc

@dataclass(frozen=True)
class Layout(sc._PackedAttentionLayout):
    tiles: torch.Tensor

def install(kernels, query_tile=8):
    old_layout = kernels.attention_layout
    old_attention = kernels.attention_packed
    kernels.tile_launches = 0
    def layout(self, spans):
        base=old_layout(spans)
        queries=0; keys=0; tiles=[]
        for length,count,past in spans:
            for first in range(0,length,query_tile):
                tiles.append([queries+first,min(query_tile,length-first),keys,count,past+first])
            queries+=length; keys+=count
        return Layout(base.ranges,base.queries,base.keys,base.max_keys,
                      torch.tensor(tiles,dtype=torch.int32,device=self.device))
    def attention(self, query,key,value,spans,repeats,scale,*,error_flag=None):
        ranges=layout(self,spans) if not isinstance(spans,sc._PackedAttentionLayout) else spans
        dim=query.shape[-1]
        shared=4*((ranges.max_keys+query_tile)*(dim+dim//32)+query_tile*ranges.max_keys)
        if not isinstance(ranges,Layout) or dim not in (32,64,128) or ranges.max_keys>256 or shared>48*1024:
            return old_attention(query,key,value,ranges,repeats,scale,error_flag=error_flag)
        query,key,value=self._float32(query,key,value)
        name=f'prefill-tile-{query_tile}-{dim}'
        if name not in self._functions:
            header=''.join(f'#define {k} 0x{v:08x}u\n' for k,v in sc.reference_constants().items())
            header+=f'#define DIM {dim}\n#define QTILE {query_tile}\n'
            source=Path(__file__).with_suffix('.cu').read_text()
            self._functions[name]=self._compile(name,header+sc._OPS_SOURCE+source,['strict_attention_prefill'],
                                                ptx_exact=sc.OPS_PTX_EXACT,sass_exact=sc.OPS_SASS_EXACT)['strict_attention_prefill']
        flag=self.new_error_flag() if error_flag is None else error_flag
        out=torch.empty((query.shape[1],query.shape[0]*dim),device=self.device,dtype=torch.float32)
        self._launch(self._functions[name],grid=(ranges.tiles.shape[0],key.shape[0],repeats),block=(32*query_tile,1),
                     pointers=(query,key,value,out,flag,ranges.tiles),
                     integers=(query.shape[0],query.shape[1],key.shape[1],repeats),floats=(scale,),shared=shared)
        self.tile_launches+=1
        self._finish(flag,error_flag)
        return out
    kernels.attention_layout=MethodType(layout,kernels)
    kernels.attention_packed=MethodType(attention,kernels)
