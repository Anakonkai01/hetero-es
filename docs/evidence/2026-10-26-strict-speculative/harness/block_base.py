"""Unselected exact multi-position scorer; no speculative acceptance policy or managed integration."""
import torch
from heteroes.eval import strict_cuda as sc
from heteroes.eval.reference_ops import ReferenceArithmeticError
from heteroes.eval.strict_decoder_graph import graph_memory_bound

class BlockVerifier:
    def __init__(self,engine,prompts,block):
        if type(block)is not int or not 1<=block<=4 or not 1<=len(prompts)*block<=128:
            raise ReferenceArithmeticError('Finite block verifier supports up to 128 query positions')
        self.engine,self.prompts,self.block=engine,prompts,block
        self.graph=self.logits=self.chosen=self.inputs=None
        self.locked=False

    def _signature(self):
        return tuple((p.data_ptr(),p._version)for p in self.engine.model.parameters())

    @torch.inference_mode()
    def __enter__(self):
        e=self.engine
        if not e._call_lock.acquire(blocking=False):raise ReferenceArithmeticError('Concurrent block verifier')
        self.locked=True
        try:
            lengths,_=e._batch_layout(self.prompts,[None]*len(self.prompts))
            if max(lengths)+self.block>e.max_context:raise ReferenceArithmeticError('Block exceeds context')
            if any(bool(((p<0)|(p>=e.config.vocab_size)).any())for p in self.prompts):
                raise ReferenceArithmeticError('Block prefix token outside vocabulary')
            bound=graph_memory_bound(e.config,len(lengths)*self.block,e.max_context,e.head_dim,
                                     prompt_tokens=sum(lengths))+e._request_workspace_bytes(len(lengths)*self.block)
            if bound>e.max_graph_bytes:raise ReferenceArithmeticError('Block scorer exceeds conservative graph budget')
            self.state=e._session_for(len(lengths));self.state.clear();e._generation_begin()
            _,caches=e.forward_batch(self.prompts);self.state.prefix(caches,lengths);del caches
            ranges=[];positions=[]
            for owner,length in enumerate(lengths):
                for offset in range(self.block):
                    ranges.append((owner*e.max_context,length+offset+1,length+offset))
                    positions.append(length+offset)
            self.ranges=torch.tensor(ranges,dtype=torch.int32,device=e.device)
            self.positions=torch.tensor(positions,dtype=torch.long,device=e.device)
            self.inputs=torch.zeros((len(lengths),self.block),dtype=torch.long,device=e.device)
            self.layout=sc._PackedAttentionLayout(self.ranges,len(positions),len(lengths)*e.max_context,max(lengths)+self.block)
            self.signature=self._signature()
            self._core();e.kernels.raise_if_error(self.state.flag)
            graph=torch.cuda.CUDAGraph()
            with torch.cuda.graph(graph):self.logits,self.chosen=self._core()
            self.graph=graph
            return self
        except BaseException:
            self.close();raise

    def _core(self):
        e=self.engine;c=e.config;kernels=e.kernels;flag=self.state.flag
        flag.zero_();heads=c.num_attention_heads;kv=c.num_key_value_heads;dim=e.head_dim
        hidden=e.model.model.embed_tokens.weight[self.inputs.reshape(-1)].float()
        cosine,sine=e._rope_cosine[self.positions],e._rope_sine[self.positions]
        eps=float(c.rms_norm_eps)
        for number,layer in enumerate(e.model.model.layers):
            attention=layer.self_attn
            normalized=kernels.rms_norm(hidden,layer.input_layernorm.weight,eps,error_flag=flag)
            q,k,v=e._decode_project_many(normalized,(attention.q_proj,attention.k_proj,attention.v_proj),flag)
            q=kernels.rope(q,cosine,sine,heads,error_flag=flag)
            k=kernels.rope(k,cosine,sine,kv,error_flag=flag)
            keys,values=self.state.caches[2*number:2*number+2]
            self.state.decode.store(k,v,self.ranges,keys,values)
            mixed=kernels.attention_packed(q,keys,values,self.layout,heads//kv,float(e._attention_scale),error_flag=flag)
            hidden=kernels.add(hidden,e._decode_project(mixed,attention.o_proj,flag),error_flag=flag)
            normalized=kernels.rms_norm(hidden,layer.post_attention_layernorm.weight,eps,error_flag=flag)
            gate,up=e._decode_project_many(normalized,(layer.mlp.gate_proj,layer.mlp.up_proj),flag)
            gated=kernels.silu_mul(gate,up,error_flag=flag)
            hidden=kernels.add(hidden,e._decode_project(gated,layer.mlp.down_proj,flag),error_flag=flag)
        normalized=kernels.rms_norm(hidden,e.model.model.norm.weight,eps,error_flag=flag)
        logits=e._decode_project(normalized,e.model.lm_head,flag)
        return logits,logits.argmax(-1).reshape(self.inputs.shape)

    @torch.inference_mode()
    def run(self,guesses):
        e=self.engine
        if not self.locked or self.graph is None:raise ReferenceArithmeticError('Closed block scorer')
        if torch.cuda.current_stream(e.device)!=self.state.stream:raise ReferenceArithmeticError('Block scorer stream changed')
        if self._signature()!=self.signature:raise ReferenceArithmeticError('Block scorer requires fixed candidate bindings/versions')
        if guesses.shape!=self.inputs.shape or guesses.dtype!=torch.long or guesses.device!=e.device:
            raise ReferenceArithmeticError('Block guesses shape/dtype/device mismatch')
        if bool(((guesses<0)|(guesses>=e.config.vocab_size)).any()):raise ReferenceArithmeticError('Invalid guess token')
        self.inputs.copy_(guesses);self.graph.replay();e.kernels.raise_if_error(self.state.flag)
        return self.logits,self.chosen

    @torch.inference_mode()
    def close(self):
        if self.locked:
            try:
                self.engine._generation_end()
                if self.engine._session is not None:self.engine._session.clear()
                for tensor in (self.inputs,self.logits,self.chosen):
                    if tensor is not None:tensor.zero_()
                torch.cuda.current_stream(self.engine.device).synchronize()
                self.graph=None
            finally:
                self.locked=False;self.engine._call_lock.release()

    def __exit__(self,*args):self.close()
