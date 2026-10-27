"""Unselected prefill-only TMA adapter; all decoder and grouped decode math stays on the baseline."""
from types import MethodType
from heteroes.eval import strict_cuda as sc
from tma_byvalue import TmaByValue

class PrefillTransport:
    def __init__(self,k):
        self.k=k;self.enabled=True;self.calls=0;self.compiled={};self.base=k._linear
        k._linear=MethodType(lambda owner,*a,**kw:self.project(*a,**kw),k)
    def project(self,value,weight,bias=None,**kw):
        rows,width,outputs=sc.validate_linear(value,weight,bias,device=self.k.device)
        if not (self.enabled and rows>128 and rows<=65535*32 and width%16==0
                and kw.get('split_k',1)==1 and kw.get('row_tile',32) in (None,32)
                and kw.get('implementation','auto')!='simt' and self.k.arch=='sm_120'
                and self.k.magnitude_bits==22):
            return self.base(value,weight,bias,**kw)
        flag=kw.get('error_flag');owned=flag is None
        if owned:flag=self.k.new_error_flag()
        prepared=kw.get('prepared')
        if prepared is None:prepared=self.k.quantize_input(value.reshape(rows,width),_packed=True,error_flag=flag)
        key=(width,bias is not None)
        if key not in self.compiled:self.compiled[key]=TmaByValue(width,64,1,2,3,has_bias=bias is not None)
        c=self.compiled[key]
        out=c.project(prepared,weight,self.k._weight_exponents(weight,flag),flag,bias)
        if kw.get('residual') is not None:out=self.k.add(kw['residual'],out,error_flag=flag)
        self.k._finish(flag,None if owned else flag)
        self.calls+=1
        return out.reshape(*value.shape[:-1],outputs)
