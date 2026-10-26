"""Unselected exact B22 proposal verification over current-candidate KV, penalty-one greedy only."""
import hashlib
from pathlib import Path
import torch
from block_base import BlockVerifier
from heteroes.canonical import canonical_json_hash
from heteroes.eval import strict_cuda as sc
from heteroes.eval.integer_decoder import IntegerDecoderGraph
from heteroes.eval.reference_ops import ReferenceArithmeticError
from heteroes.eval.strict_decoder_graph import graph_memory_bound


class LiveScorer(BlockVerifier):
    def __init__(self,engine,state,active,block):
        self.engine,self.state,self.block=engine,state,block
        self.inputs=torch.zeros((active,block),dtype=torch.long,device=engine.device)
        self.positions=torch.empty(active*block,dtype=torch.long,device=engine.device)
        self.ranges=torch.empty((active*block,3),dtype=torch.int32,device=engine.device)
        self.layout=sc._PackedAttentionLayout(self.ranges,active*block,state.capacity*engine.max_context,engine.max_context)
        self.graph=self.logits=self.chosen=self.publication=None

    def set_inputs(self,rows,owners,lengths):
        positions=[];ranges=[]
        for owner,length in zip(owners,lengths,strict=True):
            if not 0<=owner<self.state.capacity or not 0<=length<=self.engine.max_context-self.block:
                raise ReferenceArithmeticError('Invalid speculative range')
            for offset in range(self.block):
                positions.append(length+offset)
                ranges.append((owner*self.engine.max_context,length+offset+1,length+offset))
        self.inputs.copy_(torch.tensor(rows,dtype=torch.long,device=self.engine.device))
        self.positions.copy_(torch.tensor(positions,dtype=torch.long,device=self.engine.device))
        self.ranges.copy_(torch.tensor(ranges,dtype=torch.int32,device=self.engine.device))

    def capture(self):
        # Warmup may encounter invalid hypothetical future branches. Only verified actual replay is published.
        self._core()
        graph=torch.cuda.CUDAGraph()
        with torch.cuda.graph(graph):
            self.logits,self.chosen=self._core()
            self.publication=torch.cat((self.chosen.reshape(-1),self.state.flag.to(torch.int64)))
        self.graph=graph

    def score(self):
        if self.graph is None:self.capture()
        self.graph.replay()
        result=self.publication.tolist()
        status=result[-1]
        if status:
            if status&~3:self.engine.kernels.raise_if_error(self.state.flag)
            return self.first_only(),True
        count=self.inputs.shape[0]
        return [result[row*self.block:(row+1)*self.block]for row in range(count)],False

    def first_only(self):
        # Recompute the real one-token path. Later speculative positions are outside every key range.
        previous=self.inputs,self.positions,self.ranges,self.layout
        count=self.inputs.shape[0]
        try:
            self.inputs=self.inputs[:,:1].contiguous()
            self.positions=self.positions.reshape(count,self.block)[:,0].contiguous()
            self.ranges=self.ranges.reshape(count,self.block,3)[:,0].contiguous()
            self.layout=sc._PackedAttentionLayout(self.ranges,count,self.state.capacity*self.engine.max_context,self.engine.max_context)
            logits,chosen=self._core()
            self.engine.kernels.raise_if_error(self.state.flag)
            return chosen.tolist()
        finally:self.inputs,self.positions,self.ranges,self.layout=previous

    @torch.inference_mode()
    def clear_request(self):
        for tensor in (self.inputs,self.positions,self.ranges,self.logits,self.chosen,self.publication):
            if tensor is not None:tensor.zero_()


class SuffixProposer:
    def __init__(self,prior_rows,*,min_match=2,max_match=8,max_source_tokens=32768):
        if not 1<=min_match<=max_match<=8:raise ValueError('Invalid suffix lengths')
        if sum(len(tokens)for row in prior_rows for tokens in row)>max_source_tokens:
            raise ValueError('Proposal source-token budget exceeded')
        self.min_match,self.max_match=min_match,max_match
        self.lookup=[]
        for row in prior_rows:
            lookup={}
            for sequence in row:
                sequence=tuple(sequence)
                if any(type(t)is not int or t<0 for t in sequence):raise ValueError('Invalid prior token')
                for n in range(min_match,max_match+1):
                    for first in range(len(sequence)-n):lookup[sequence[first:first+n]]=(sequence,first+n)
            self.lookup.append(lookup)

    def __call__(self,owner,output,count):
        for n in range(min(self.max_match,len(output)),self.min_match-1,-1):
            match=self.lookup[owner].get(tuple(output[-n:]))
            if match is not None:
                sequence,first=match
                return sequence[first:first+count]
        return ()


class SpeculativeGraph(IntegerDecoderGraph):
    def __init__(self,*args,block=2,pad_completed=True,**kwargs):
        if type(block)is not int or block not in (1,2,4):raise ReferenceArithmeticError('Unsupported speculative block')
        if type(pad_completed)is not bool:raise ReferenceArithmeticError('Invalid completed-row policy')
        self.block=block;self.pad_completed=pad_completed;self._spec=None;self._spec_key=None;self.capture_count=0
        super().__init__(*args,**kwargs)
        self.identity={**self.identity,'backend':'decoder_b22_suffix_verification_probe',
                       'speculativeBlock':block,'padCompletedWithOwnPrompt':pad_completed,'maxRetainedSpecCaptures':1,
                       'speculativeSourceSha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
        self.fingerprint=canonical_json_hash(self.identity)

    def request_buffers(self):
        if self._spec is None:return ()
        return tuple(t for t in (self._spec.inputs,self._spec.positions,self._spec.ranges,self._spec.logits,
                                self._spec.chosen,self._spec.publication)if t is not None)

    def _release_graph(self):
        if self._spec is not None:
            self._spec.state.stream.synchronize()
            with torch.cuda.stream(self._spec.state.stream):self._spec.clear_request()
            self._spec.state.stream.synchronize()
            self._spec=None;self._spec_key=None
        super()._release_graph()

    def _scorer(self,state,active,block):
        metadata=tuple(t.data_ptr()for t in self.kernels.weight_metadata_buffers())
        key=(id(state),active,block,metadata)
        if self._spec_key!=key:
            if self._spec is not None:self._spec.clear_request()
            self._spec=LiveScorer(self,state,active,block);self._spec_key=key
        return self._spec

    @torch.inference_mode()
    def generate(self,input_ids,attention_mask=None,*,proposer=None,**options):
        self.stats={'rounds':0,'acceptedDraftTokens':0,'proposedTokens':0,'numericFallbacks':0,'captures':0,'dummyPrefixRows':0}
        max_new=options.get('max_new_tokens',16)
        if options.get('repetition_penalty',1.)!=1. or options.get('use_cache',True)is not True:
            self.stats['ordinaryFallback']=True
            return super().generate(input_ids,attention_mask,**options)
        histories,ends,pad,penalty=self._prepare_generation(input_ids,attention_mask,**options)
        if proposer is not None and not callable(proposer):raise ReferenceArithmeticError('Invalid proposal provider')
        if len(histories)*self.block>128:raise ReferenceArithmeticError('Speculative query budget exceeded')
        if not self._call_lock.acquire(blocking=False):raise ReferenceArithmeticError('Concurrent speculative use')
        try:
            lengths=[row.shape[1]for row in histories];capacity=len(histories)
            prompt_tokens=[row[0].tolist()for row in histories]
            bound=graph_memory_bound(self.config,capacity*self.block,self.max_context,self.head_dim,
                                     prompt_tokens=sum(lengths))+self._request_workspace_bytes(capacity*self.block)
            if bound>self.max_graph_bytes:raise ReferenceArithmeticError('Speculative graph budget exceeded')
            state=self._session_for(capacity);state.clear();self._generation_begin()
            scores,caches=self.forward_batch(histories);state.prefix(caches,lengths);del caches
            outputs=[[token]for token in scores.argmax(-1).tolist()];del scores
            active=[i for i,row in enumerate(outputs)if row[-1]not in ends and len(row)<max_new]
            while active:
                current=[lengths[owner]+len(outputs[owner])-1 for owner in active]
                block=self.block if all(n+self.block<=self.max_context for n in current)else 1
                live=set(active)
                owners=(list(range(capacity))if self.pad_completed and all(
                    lengths[owner]>=block for owner in range(capacity)if owner not in live)else active)
                current=[lengths[owner]+len(outputs[owner])-1 if owner in live else lengths[owner]-block for owner in owners]
                guesses=[];drafts=[]
                for owner in owners:
                    if owner not in live:
                        # Recompute real prompt positions: no post-EOS branch and no cache alias with a live owner.
                        guesses.append(prompt_tokens[owner][-block:]);drafts.append([])
                        self.stats['dummyPrefixRows']+=1
                        continue
                    count=min(block-1,max_new-len(outputs[owner])-1)
                    proposal=()if proposer is None else proposer(owner,tuple(outputs[owner]),count)
                    if not isinstance(proposal,(list,tuple))or len(proposal)>count or any(
                        type(t)is not int or not 0<=t<self.config.vocab_size for t in proposal):
                        raise ReferenceArithmeticError('Invalid proposal tokens')
                    draft=list(proposal);drafts.append(draft)
                    guesses.append([outputs[owner][-1],*draft,*([0]*(block-1-len(draft)))])
                scorer=self._scorer(state,len(owners),block);scorer.set_inputs(guesses,owners,current)
                capture=scorer.graph is None
                predictions,fallback=scorer.score()
                self.stats['rounds']+=1;self.stats['numericFallbacks']+=int(fallback)
                self.stats['proposedTokens']+=sum(map(len,drafts))
                self.stats['captures']+=int(capture);self.capture_count+=int(capture)
                for owner,predicted,draft in zip(owners,predictions,drafts,strict=True):
                    if owner not in live:continue
                    accepted=0
                    if not fallback:
                        for guess,actual in zip(draft,predicted):
                            if guess!=actual:break
                            accepted+=1
                    emitted=predicted[:accepted+1]
                    for index,token in enumerate(emitted):
                        outputs[owner].append(token)
                        if index<accepted:self.stats['acceptedDraftTokens']+=1
                        if token in ends or len(outputs[owner])==max_new:break
                active=[i for i in active if outputs[i][-1]not in ends and len(outputs[i])<max_new]
            completion=torch.full((capacity,max(map(len,outputs))),pad,dtype=torch.long,device=self.device)
            for i,row in enumerate(outputs):completion[i,:len(row)]=torch.tensor(row,dtype=torch.long,device=self.device)
            return torch.cat((input_ids,completion),dim=1)
        except BaseException:
            self._release_graph();raise
        finally:
            try:
                self._generation_end()
                if self._session is not None:self._session.clear()
                if self._spec is not None:self._spec.clear_request()
                torch.cuda.current_stream(self.device).synchronize()
            finally:self._call_lock.release()
