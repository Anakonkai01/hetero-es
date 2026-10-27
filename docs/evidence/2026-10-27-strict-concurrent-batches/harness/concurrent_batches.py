"""Independent request owners share read-only live weights, with one persistent host worker and stream each."""
from concurrent.futures import ThreadPoolExecutor
import threading
import torch

class ConcurrentRequests:
    def __init__(self,engines,factory):
        self.engines=tuple(engines);self.factory=factory
        assert len(self.engines)>1
        self.streams=tuple(torch.cuda.Stream(device=e.device) for e in self.engines)
        self.pool=ThreadPoolExecutor(max_workers=len(engines));self.lock=threading.Lock()
        self.warm_key=None;self.warm_count=0
    def _worker(self,index,rows,tokens,barrier):
        engine,stream=self.engines[index],self.streams[index]
        with torch.inference_mode(),torch.cuda.device(engine.device),torch.cuda.stream(stream):
            # Ensure both request owners are ready before either submits its prefill.
            if barrier is not None:barrier.wait(timeout=30)
            return self.factory(engine,tokens)(rows)
    def run(self,rows,tokens):
        with self.lock:
            assert len(rows)>=len(self.engines)
            barrier=threading.Barrier(len(self.engines));size=-(-len(rows)//len(self.engines))
            groups=[rows[i*size:min(len(rows),(i+1)*size)] for i in range(len(self.engines))]
            assert all(groups)
            key=(tuple(map(len,rows)),tokens,tuple((id(p),p.data_ptr(),tuple(p.shape)) for p in self.engines[0].model.parameters()))
            if self.warm_key!=key:
                # Torch graph capture is globally sensitive to unrelated stream activity. Capture each
                # owner in isolation; later requests only replay those already initialized graphs.
                for i,group in enumerate(groups):self.pool.submit(self._worker,i,group,tokens,None).result()
                self.warm_key=key;self.warm_count+=1
            futures=[self.pool.submit(self._worker,i,group,tokens,barrier) for i,group in enumerate(groups)]
            return [row for f in futures for row in f.result()]
    def close(self):
        self.pool.shutdown(wait=True)
        for stream in self.streams:stream.synchronize()
