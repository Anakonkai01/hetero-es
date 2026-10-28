#!/usr/bin/env python3
"""Does reading the 'finished' flags back to the host only every k steps (instead of at every step) change the texts or the time? Qwen2.5-0.5B FP32, parent weights, 128 questions,
chunk 64 and 128, the arithmetic questions of the project (short answers) and GSM8K (long answers). Texts are compared with check_every = 1 AND with the library's generate().
    python bench_check_every.py --model-path DIR --gsm8k-file F --out result.json"""
import argparse, copy, json, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import compact_general as cg


def main(argv):
    p = argparse.ArgumentParser(); p.add_argument("--model-path", required=True); p.add_argument("--gsm8k-file", required=True); p.add_argument("--out", required=True)
    p.add_argument("--ks", default="1,4,8,16"); p.add_argument("--repeats", type=int, default=3)
    a = p.parse_args(argv)
    if Path(a.out).exists():
        print("error: output exists", file=sys.stderr); return 2
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    tok = AutoTokenizer.from_pretrained(a.model_path)
    model = AutoModelForCausalLM.from_pretrained(a.model_path, dtype=torch.float32).to("cuda").eval()
    gen = copy.deepcopy(model.generation_config); gen.do_sample = False; gen.max_new_tokens = 512
    pad, eos = gen.pad_token_id, list(gen.eos_token_id)
    processors = model._get_logits_processor(gen, 1, None, None, [])
    result = []
    for task in ("arith", "gsm8k"):
        raw = cg.questions_for(task, 128, 20261009, a.gsm8k_file)
        prompts = [tok.apply_chat_template([{"role": "system", "content": cg.SYSTEM}, {"role": "user", "content": q}], tokenize=False, add_generation_prompt=True) for q in raw]
        max_new = 256 if task == "arith" else 512
        for chunk in (64, 128):
            def run(k):
                texts = []
                for s in range(0, 128, chunk):
                    part, _, _ = cg.compact_generate(model, tok, prompts[s:s + chunk], processors, eos, pad, max_new, 0.1, k)
                    texts += part
                return texts
            base = run(1)
            for k in [int(x) for x in a.ks.split(",")]:
                times = []
                for _ in range(a.repeats):
                    torch.cuda.synchronize(); t = time.perf_counter(); texts = run(k); torch.cuda.synchronize(); times.append(time.perf_counter() - t)
                same = texts == base
                result.append({"task": task, "chunk": chunk, "check_every": k, "seconds_min": min(times), "seconds_all": times, "same_as_k1": same})
                print(f"{task} chunk {chunk} check_every {k}: min {min(times):.3f} s of {a.repeats}, same texts as k=1: {same}", flush=True)
    Path(a.out).write_text(json.dumps({"gpu": torch.cuda.get_device_name(0), "records": result}, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
