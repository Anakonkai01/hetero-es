"""Existing integer instruction policy plus the exact non-arithmetic async memory-fence opcode."""
import re
import subprocess
import tempfile
from pathlib import Path
from heteroes.eval import strict_cuda as sc
from heteroes.eval.integer_cuda import IntegerCudaKernels

def audit_integer(text):
    result=sc.audit_sass(text,exact=('F2I.NTZ','FENCE.VIEW.ASYNC.S'))
    result['integerMmaOps']=len(re.findall(r'\bIMMA(?:\.[A-Z0-9_]+)*\s',text))
    if not result['integerMmaOps']:result['violations'].append('Missing integer IMMA')
    if result['floatOps'].get('FMUL',0):result['violations'].append('Floating multiply in integer projection')
    return result

class TmaOwner(IntegerCudaKernels):
    def _audit_cubin(self,cubin,exact=(),*,integer_mma=False):
        if not integer_mma:return super()._audit_cubin(cubin,exact,integer_mma=False)
        if not self._nvdisasm:raise RuntimeError('TMA prototype requires its SASS audit')
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'kernel.cubin';path.write_bytes(cubin)
            text=subprocess.run([self._nvdisasm,str(path)],capture_output=True,text=True,check=True).stdout
        return audit_integer(text)
