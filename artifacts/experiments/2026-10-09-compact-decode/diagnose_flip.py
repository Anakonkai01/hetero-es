#!/usr/bin/env python3
"""Why did one GSM8K answer differ (Qwen2.5-0.5B, FP32, candidate seed 7002, chunk 128, question 15)? Rebuilds that candidate exactly as compact_general.py does, answers question 15 in
five ways (the library at chunk 128, 64 and 1; the compacting decoder at chunk 128 and 64), prints where the texts first differ and the margin between the two best scores at that step
(teacher-forced, one sequence). A flip at a margin of the order of the FP32 rounding noise means: any change of the batch shape can do it, not only the compaction."""
import copy, sys, torch
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
import compact_general as cg
from transformers import AutoModelForCausalLM, AutoTokenizer

MODEL, GSM, SEED, QUESTION = sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4])
tok = AutoTokenizer.from_pretrained(MODEL)
model = AutoModelForCausalLM.from_pretrained(MODEL, dtype=torch.float32).to("cuda").eval()
gen = copy.deepcopy(model.generation_config); gen.do_sample = False; gen.max_new_tokens = 512
pad, eos = gen.pad_token_id, list(gen.eos_token_id)
processors = model._get_logits_processor(gen, 1, None, None, [])
raw = cg.questions_for("gsm8k", 128, 20261009, GSM)
prompts = [tok.apply_chat_template([{"role": "system", "content": cg.SYSTEM}, {"role": "user", "content": q}], tokenize=False, add_generation_prompt=True, enable_thinking=False) for q in raw]
g = torch.Generator(device="cpu").manual_seed(SEED)
with torch.no_grad():
    for p in model.parameters():
        p.add_((torch.randn(p.shape, generator=g, dtype=torch.float32) * 1e-3).to(device=p.device, dtype=p.dtype))

def library(chunk, indices):
    tok.padding_side = "left"
    texts = {}
    for s in range(0, 128, chunk):
        part = list(range(s, min(s + chunk, 128)))
        if not set(indices) & set(part):
            continue
        inp = tok([prompts[i] for i in part], return_tensors="pt", padding=True).to("cuda")
        with torch.no_grad():
            ids = model.generate(**inp, max_new_tokens=512, do_sample=False, pad_token_id=pad)
        out = [t.strip() for t in tok.batch_decode(ids[:, inp["input_ids"].shape[1]:], skip_special_tokens=True)]
        for i, t in zip(part, out):
            texts[i] = t
    return texts

def compact(chunk, indices):
    texts = {}
    for s in range(0, 128, chunk):
        part = list(range(s, min(s + chunk, 128)))
        if not set(indices) & set(part):
            continue
        out, _, _ = cg.compact_generate(model, tok, [prompts[i] for i in part], processors, eos, pad, 512, 0.1)
        for i, t in zip(part, out):
            texts[i] = t
    return texts

q = QUESTION
results = {"library128": library(128, [q])[q], "library64": library(64, [q])[q], "library1": library(1, [q])[q],
           "compact128": compact(128, [q])[q], "compact64": compact(64, [q])[q]}
names = list(results)
for n in names:
    print(f"{n:11s} equal to library128: {results[n] == results['library128']}   length {len(results[n])}")
base = results["library128"]
for n in names[1:]:
    other = results[n]
    if other != base:
        k = next((i for i, (a, b) in enumerate(zip(base, other)) if a != b), min(len(base), len(other)))
        print(f"first difference library128 / {n} at character {k}: ...{base[max(0,k-40):k+30]!r}  /  ...{other[max(0,k-40):k+30]!r}")
        prefix = tok.apply_chat_template([{"role": "system", "content": cg.SYSTEM}, {"role": "user", "content": raw[q]}], tokenize=False, add_generation_prompt=True, enable_thinking=False) + base[:k]
        ids = tok(prefix, return_tensors="pt").to("cuda")
        with torch.no_grad():
            logits = model(**ids).logits[0, -1].float()
        logits = processors(ids["input_ids"], logits[None])[0]
        top = torch.topk(logits, 3)
        print("   top-3 scores at that step (after the repetition penalty, teacher-forced, one sequence):", [(tok.decode([int(i)]), round(float(v), 6)) for v, i in zip(top.values, top.indices)], "margin", float(top.values[0] - top.values[1]))
