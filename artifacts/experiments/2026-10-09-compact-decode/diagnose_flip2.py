#!/usr/bin/env python3
"""Second look at the flip of diagnose_flip.py, with token ids (no re-tokenization). Generates question 15 of candidate 7002 with the library at chunk 128 and at chunk 64, finds the first
generated token that differs, and scores that step with ONE unpadded sequence (the same prefix of ids) in FP32: the scores of the two tokens, after the repetition penalty."""
import copy, sys, torch
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
import compact_general as cg
from transformers import AutoModelForCausalLM, AutoTokenizer

MODEL, GSM, SEED, Q = sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4])
tok = AutoTokenizer.from_pretrained(MODEL)
model = AutoModelForCausalLM.from_pretrained(MODEL, dtype=torch.float32).to("cuda").eval()
gen = copy.deepcopy(model.generation_config); gen.do_sample = False; gen.max_new_tokens = 512
pad = gen.pad_token_id
processors = model._get_logits_processor(gen, 1, None, None, [])
raw = cg.questions_for("gsm8k", 128, 20261009, GSM)
prompts = [tok.apply_chat_template([{"role": "system", "content": cg.SYSTEM}, {"role": "user", "content": q}], tokenize=False, add_generation_prompt=True, enable_thinking=False) for q in raw]
g = torch.Generator(device="cpu").manual_seed(SEED)
with torch.no_grad():
    for p in model.parameters():
        p.add_((torch.randn(p.shape, generator=g, dtype=torch.float32) * 1e-3).to(device=p.device, dtype=p.dtype))
tok.padding_side = "left"

def ids_at(chunk):
    start = (Q // chunk) * chunk
    part = list(range(start, min(start + chunk, 128)))
    inp = tok([prompts[i] for i in part], return_tensors="pt", padding=True).to("cuda")
    with torch.no_grad():
        out = model.generate(**inp, max_new_tokens=512, do_sample=False, pad_token_id=pad)
    row = out[part.index(Q), inp["input_ids"].shape[1]:]
    return row[row != pad].tolist()

a, b = ids_at(128), ids_at(64)
k = next((i for i, (x, y) in enumerate(zip(a, b)) if x != y), None)
print("lengths", len(a), len(b), "first different generated token index", k)
if k is not None:
    prompt_ids = tok(prompts[Q], return_tensors="pt")["input_ids"].to("cuda")
    prefix = torch.cat([prompt_ids, torch.tensor([a[:k]], device="cuda", dtype=torch.long)], dim=1)
    with torch.no_grad():
        logits = model(input_ids=prefix, use_cache=False).logits[:, -1].float()
    scores = processors(prefix, logits)[0]
    print("token chosen at chunk 128:", repr(tok.decode([a[k]])), "score", float(scores[a[k]]), "| at chunk 64:", repr(tok.decode([b[k]])), "score", float(scores[b[k]]))
    print("difference of the two scores (one unpadded sequence, FP32):", float(scores[a[k]] - scores[b[k]]))
    top = torch.topk(scores, 3)
    print("top-3 of the unpadded sequence:", [(tok.decode([int(i)]), round(float(v), 5)) for v, i in zip(top.values, top.indices)])
