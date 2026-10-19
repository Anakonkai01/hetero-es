import time, statistics, torch
from heteroes.model.loading import load_pinned_model
from heteroes.eval.precision import EvalModel
from heteroes.eval.cot_workload import make_questions, SYSTEM_PROMPT, MAX_NEW_TOKENS
S="/home/pc5070ti/.cache/huggingface/hub/models--Qwen--Qwen2.5-0.5B-Instruct/snapshots/7ae557604adf67be50417f59c2c2f167def9a775"
loaded=load_pinned_model(S,"cuda"); tok=loaded.tokenizer
ev=EvalModel(loaded.model,"float32"); ev.refresh(); model=ev.model
qs=[q for q,_ in make_questions(128,1)]
tok.padding_side="left"
def run(chunk):
    lens=[]; steps=[]; times=[]; plen=[]
    for s in range(0,128,chunk):
        g=qs[s:s+chunk]
        prompts=[tok.apply_chat_template([{"role":"system","content":SYSTEM_PROMPT},{"role":"user","content":q}],tokenize=False,add_generation_prompt=True) for q in g]
        inp=tok(prompts,return_tensors="pt",padding=True); inp={k:v.cuda() for k,v in inp.items()}
        torch.cuda.synchronize(); t=time.perf_counter()
        with torch.no_grad(): ids=model.generate(**inp,max_new_tokens=MAX_NEW_TOKENS,do_sample=False)
        torch.cuda.synchronize(); times.append(time.perf_counter()-t)
        new=ids[:,inp["input_ids"].shape[1]:]
        # real length of each answer = position of the first pad/eos
        for row in new:
            n=(row!=tok.pad_token_id).sum().item(); lens.append(n)
        steps.append(new.shape[1]); plen.append(inp["input_ids"].shape[1])
    return lens,steps,times,plen
run(64)  # warm-up
for chunk in (64,128):
    lens,steps,times,plen=run(chunk)
    tot_slots=sum(s*min(chunk,128) for s in steps) if chunk==128 else sum(s*64 for s in steps)
    print(f"chunk {chunk}: calls={len(steps)} steps per call={steps} prompt_len={plen} time per call={[round(x,2) for x in times]}")
    print(f"  answer tokens: mean={statistics.mean(lens):.1f} median={statistics.median(lens)} max={max(lens)} min={min(lens)}; answers hitting 256: {sum(l>=256 for l in lens)}")
    print(f"  slots used {sum(lens)} of {tot_slots} => useful fraction {sum(lens)/tot_slots:.2f}; ms per step: {[round(1000*t/s,1) for t,s in zip(times,steps)]}")
