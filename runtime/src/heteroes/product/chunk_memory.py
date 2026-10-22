"""
How much GPU memory and time one generate() call of `chunk` prompts takes on this device, for one model, measured while
the device qualifies for that model (owner 2026-10-22: suggest a batch and its chunks from what each GPU measured, so a
GPU nobody has seen before, a 32 GB 5090 for example, gets a suggestion from its own numbers).

The shape is fixed: `prompt_tokens` prompt tokens and exactly `new_tokens` new tokens per prompt, the model held as a run
holds it (the FP16 weights plus the FP32 copy that evaluates). Memory beyond the weights grows with the number of tokens,
so `suggest` (heteroes.sdk_lab) scales the measured excess to a recipe's own lengths. A chunk that runs out of memory
ends the sweep: the larger ones would too.
"""

import copy
import time

CHUNKS = (16, 32, 64, 128)
PROMPT_TOKENS = 200
NEW_TOKENS = 256
FORMAT = 1


def measure(model_path, files, device="cuda", chunks=CHUNKS, prompt_tokens=PROMPT_TOKENS, new_tokens=NEW_TOKENS):
    import torch

    from heteroes.v3.model import load

    live, tokenizer = load(model_path, files, device)
    model = copy.deepcopy(live).float()  # as EvalModel holds it for FP32 evaluation
    torch.cuda.synchronize()
    base = torch.cuda.memory_allocated()
    token = tokenizer("the", add_special_tokens=False)["input_ids"][0]
    results = []
    for chunk in sorted(chunks):
        ids = torch.full((chunk, prompt_tokens), token, dtype=torch.long, device=device)
        torch.cuda.empty_cache()
        torch.cuda.reset_peak_memory_stats()
        start = time.perf_counter()
        try:
            with torch.no_grad():
                model.generate(
                    input_ids=ids,
                    attention_mask=torch.ones_like(ids),
                    max_new_tokens=new_tokens,
                    min_new_tokens=new_tokens,
                    do_sample=False,
                    pad_token_id=tokenizer.pad_token_id,
                )
            torch.cuda.synchronize()
        except torch.OutOfMemoryError:
            results.append({"chunk": chunk, "ran": False, "peakBytes": None, "seconds": None})
            break
        finally:
            del ids
        results.append(
            {
                "chunk": chunk,
                "ran": True,
                "peakBytes": int(torch.cuda.max_memory_allocated()),
                "seconds": round(time.perf_counter() - start, 3),
            }
        )
    total = torch.cuda.get_device_properties(torch.device(device)).total_memory
    del model, live
    torch.cuda.empty_cache()
    return {
        "formatVersion": FORMAT,
        "promptTokens": prompt_tokens,
        "newTokens": new_tokens,
        "baseBytes": int(base),
        "totalBytes": int(total),
        "chunks": results,
    }


def check(value):
    """A reported measurement, or ValueError: the lab keeps only this small, numeric shape."""
    if not isinstance(value, dict) or set(value) != {
        "formatVersion",
        "promptTokens",
        "newTokens",
        "baseBytes",
        "totalBytes",
        "chunks",
    }:
        raise ValueError("unknown chunk measurement")
    if value["formatVersion"] != FORMAT or not isinstance(value["chunks"], list) or len(value["chunks"]) > 8:
        raise ValueError("unknown chunk measurement")
    for key in ("promptTokens", "newTokens", "baseBytes", "totalBytes"):
        if type(value[key]) is not int or not 0 < value[key] < 2**50:
            raise ValueError("unknown chunk measurement")
    for item in value["chunks"]:
        if not isinstance(item, dict) or set(item) != {"chunk", "ran", "peakBytes", "seconds"}:
            raise ValueError("unknown chunk measurement")
        if type(item["chunk"]) is not int or not 1 <= item["chunk"] <= 1024 or type(item["ran"]) is not bool:
            raise ValueError("unknown chunk measurement")
        if item["ran"] and (
            type(item["peakBytes"]) is not int
            or not 0 < item["peakBytes"] < 2**50
            or type(item["seconds"]) not in (int, float)
            or not 0 <= item["seconds"] < 1e6
        ):
            raise ValueError("unknown chunk measurement")
    return value
