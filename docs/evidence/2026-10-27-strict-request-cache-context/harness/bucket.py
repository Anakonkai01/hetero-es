"""Unselected physical KV allocation sized to a validated request; configured limits/admission stay fixed."""
import hashlib
import inspect
from pathlib import Path
import textwrap
import threading
import weakref
import torch
from heteroes.canonical import canonical_json_hash
from heteroes.eval import strict_cuda as sc,strict_decoder_graph as sdg
from heteroes.eval.integer_decoder import IntegerDecoderGraph
from heteroes.eval.reference_ops import ReferenceArithmeticError

class _View:
    def __init__(self,backend,context):self.actual=backend;self.max_context=context
    def __getattr__(self,name):return getattr(self.actual,name)

def new_session(backend,capacity,signature,context):
    view=_View(backend,context)
    state=sdg._DecodeSession(view,capacity,signature)
    state.backend=weakref.proxy(backend)
    return state

SESSION=textwrap.dedent(inspect.getsource(sdg.StrictDecoderGraph._session_for))
old='self._session.capacity != capacity or self._session.signature != signature or self._session.stream != stream'
assert SESSION.count(old)==1
SESSION=SESSION.replace(old,'self._session.context != self._request_context or '+old)
old='_DecodeSession(self, capacity, signature)'
assert SESSION.count(old)==1
SESSION=SESSION.replace(old,'new_session(self, capacity, signature, self._request_context)')
scope={**vars(sdg),'new_session':new_session}
exec(SESSION,scope)
CORE=textwrap.dedent(inspect.getsource(sdg.StrictDecoderGraph._decode_core))
assert CORE.count('self.max_context')==3
CORE=CORE.replace('self.max_context','state.context')
exec(CORE,scope)

class BucketGraph(IntegerDecoderGraph):
    _session_for=scope['_session_for']
    _decode_core=scope['_decode_core']
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self._request_context=self.max_context;self._bucket_lock=threading.Lock()
        self.identity={**self.identity,'physicalCacheContext':'ceil_request_budget_to_16_with_configured_admission_v1_probe',
                       'bucketSourceSha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
        self.fingerprint=canonical_json_hash(self.identity)
    def _prepare_generation(self,*args,**kwargs):
        result=super()._prepare_generation(*args,**kwargs)
        needed=max(row.shape[1] for row in result[0])+kwargs.get('max_new_tokens',16)
        self._request_context=min(self.max_context,-(-needed//16)*16)
        return result
    @torch.inference_mode()
    def generate(self,*args,**kwargs):
        if not self._bucket_lock.acquire(blocking=False):raise ReferenceArithmeticError('Captured decode refuses concurrent use')
        try:return super().generate(*args,**kwargs)
        finally:self._bucket_lock.release()
