#!/usr/bin/env python3
"""How often does the TEXT change when only the batch shape changes? For one model and one task, over the parent and N noisy candidates (as compact_general.py), the texts of
 library chunk 64, library chunk 128, compact chunk 64 and compact chunk 128 are compared pairwise; the first pair (library 64 against library 128) uses no compaction at all.
    python batch_shape_sensitivity.py --model-path DIR --task gsm8k --gsm8k-file F --candidates 2 --max-new-tokens 512 --out result.json"""
import argparse, copy, itertools, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import compact_general as cg


def main(argv):
    p = argparse.ArgumentParser()
    p.add_argument("--model-path", required=True); p.add_argument("--task", required=True); p.add_argument("--gsm8k-file", default=None)
    p.add_argument("--count", type=int, default=128); p.add_argument("--candidates", type=int, default=2); p.add_argument("--max-new-tokens", type=int, default=512)
    p.add_argument("--chunks", default="64,128"); p.add_argument("--dtype", default="float32"); p.add_argument("--out", required=True)
    a = p.parse_args(argv)
    if Path(a.out).exists():
        print("error: output exists", file=sys.stderr); return 2
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    tok = AutoTokenizer.from_pretrained(a.model_path)
    model = AutoModelForCausalLM.from_pretrained(a.model_path, dtype=getattr(torch, a.dtype)).to("cuda").eval()
    gen = copy.deepcopy(model.generation_config); gen.do_sample = False; gen.max_new_tokens = a.max_new_tokens
    pad = gen.pad_token_id if gen.pad_token_id is not None else (tok.pad_token_id if tok.pad_token_id is not None else tok.eos_token_id)
    eos = gen.eos_token_id if gen.eos_token_id is not None else tok.eos_token_id
    eos_ids = list(eos) if isinstance(eos, (list, tuple)) else [eos]
    if tok.pad_token_id is None:
        tok.pad_token = tok.eos_token
    processors = model._get_logits_processor(gen, 1, None, None, [])
    raw = cg.questions_for(a.task, a.count, 20261009, a.gsm8k_file)
    prompts = [tok.apply_chat_template([{"role": "system", "content": cg.SYSTEM}, {"role": "user", "content": q}], tokenize=False, add_generation_prompt=True, enable_thinking=False) for q in raw]
    chunks = [int(c) for c in a.chunks.split(",")]
    original = {n: q.detach().clone() for n, q in model.named_parameters()}

    def library(chunk):
        tok.padding_side = "left"; texts = []
        for s in range(0, len(prompts), chunk):
            inp = tok(prompts[s:s + chunk], return_tensors="pt", padding=True).to("cuda")
            with torch.no_grad():
                ids = model.generate(**inp, max_new_tokens=a.max_new_tokens, do_sample=False, pad_token_id=pad)
            texts += [t.strip() for t in tok.batch_decode(ids[:, inp["input_ids"].shape[1]:], skip_special_tokens=True)]
        return texts

    def compact(chunk):
        texts = []
        for s in range(0, len(prompts), chunk):
            part, _, _ = cg.compact_generate(model, tok, prompts[s:s + chunk], processors, eos_ids, pad, a.max_new_tokens, 0.1)
            texts += part
        return texts

    records = []
    for index in range(a.candidates + 1):
        seed = None if index == 0 else 7000 + index
        if seed is not None:
            g = torch.Generator(device="cpu").manual_seed(seed)
            with torch.no_grad():
                for q in model.parameters():
                    q.add_((torch.randn(q.shape, generator=g, dtype=torch.float32) * 1e-3).to(device=q.device, dtype=q.dtype))
        try:
            variants = {}
            for c in chunks:
                variants[f"library{c}"] = library(c)
                variants[f"compact{c}"] = compact(c)
            pairs = {f"{x} vs {y}": sum(u != v for u, v in zip(variants[x], variants[y])) for x, y in itertools.combinations(variants, 2)}
            records.append({"seed": seed, "pairs": pairs})
            print(seed, pairs, flush=True)
        finally:
            if seed is not None:
                with torch.no_grad():
                    for n, q in model.named_parameters():
                        q.copy_(original[n])
    Path(a.out).write_text(json.dumps({"model": a.model_path, "task": a.task, "dtype": a.dtype, "records": records}, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
