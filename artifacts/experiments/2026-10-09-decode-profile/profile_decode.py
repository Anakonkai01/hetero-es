#!/usr/bin/env python3
"""Where does the time of one candidate's rollout go? torch.profiler over ONE compacting-decoder call (64 questions of cot_l1_q128, FP32, the parent weights, 5070 Ti), CPU and CUDA.
    python profile_decode.py --model-path DIR --chunk 64 --out DIR/profile.txt
Prints (and writes): wall time, total CUDA kernel time (GPU busy fraction), number of kernel launches, the top kernels and the top operators by CUDA time, and the same for
CPU time, so that 'launch bound' (GPU idle between kernels) can be told from 'kernel bound'. The output file must not exist."""
import argparse, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "2026-10-09-compact-decode"))
import compact_general as cg


def main(argv):
    p = argparse.ArgumentParser()
    p.add_argument("--model-path", required=True); p.add_argument("--chunk", type=int, default=64); p.add_argument("--out", required=True)
    p.add_argument("--dtype", default="float32")
    a = p.parse_args(argv)
    if Path(a.out).exists():
        print("error: output exists", file=sys.stderr); return 2
    import copy, torch
    from torch.profiler import ProfilerActivity, profile
    from transformers import AutoModelForCausalLM, AutoTokenizer
    tok = AutoTokenizer.from_pretrained(a.model_path)
    model = AutoModelForCausalLM.from_pretrained(a.model_path, dtype=getattr(torch, a.dtype)).to("cuda").eval()
    gen = copy.deepcopy(model.generation_config); gen.do_sample = False; gen.max_new_tokens = 256
    pad, eos = gen.pad_token_id, list(gen.eos_token_id)
    processors = model._get_logits_processor(gen, 1, None, None, [])
    prompts = [tok.apply_chat_template([{"role": "system", "content": "Solve the problem step by step. End your reply with a line 'Answer: <integer>'."}, {"role": "user", "content": q}],
                                       tokenize=False, add_generation_prompt=True) for q in cg.questions_for("arith", 128, 20261009, None)][:a.chunk]
    for _ in range(2):                                            # warm-up
        cg.compact_generate(model, tok, prompts, processors, eos, pad, 256, 0.1)
    torch.cuda.synchronize()
    start = time.perf_counter()
    texts, counters, lengths = cg.compact_generate(model, tok, prompts, processors, eos, pad, 256, 0.1)
    torch.cuda.synchronize()
    plain = time.perf_counter() - start
    with profile(activities=[ProfilerActivity.CPU, ProfilerActivity.CUDA]) as prof:
        t0 = time.perf_counter()
        cg.compact_generate(model, tok, prompts, processors, eos, pad, 256, 0.1)
        torch.cuda.synchronize()
        wall = time.perf_counter() - t0
    from torch.autograd import DeviceType
    events = prof.key_averages()
    kernels = [e for e in events if e.device_type == DeviceType.CUDA]           # only the kernel rows: an operator row also holds the time of its kernels
    cuda_total = sum(e.self_device_time_total for e in kernels) / 1e6
    launches = sum(e.count for e in kernels)
    lines = [f"model {a.model_path}  dtype {a.dtype}  chunk {a.chunk}  steps {counters['steps']}  slot-steps {counters['slot_steps']}  compactions {counters['compactions']}",
             f"wall without profiler {plain:.3f} s; wall under the profiler {wall:.3f} s; total CUDA kernel time {cuda_total:.3f} s ({100 * cuda_total / wall:.0f} percent of the wall)",
             f"kernel launches (count of events with device time) {launches}, per decoding step {launches / counters['steps']:.0f}", ""]
    lines.append("TOP BY SELF CUDA TIME")
    lines.append(events.table(sort_by="self_device_time_total", row_limit=18, max_name_column_width=70))
    lines.append("TOP BY SELF CPU TIME")
    lines.append(events.table(sort_by="self_cpu_time_total", row_limit=12, max_name_column_width=70))
    Path(a.out).write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines[:3]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
