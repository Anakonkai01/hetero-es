"""Greedy accuracy and sampled pass@k are recorded separately, with raw outputs."""

from collections import Counter
import math
import re
from .data import answer, sha


def extract(text):
    matches = re.findall(r"Answer:\s*\$?\s*(-?\d[\d,]*(?:\.\d+)?)", text)
    if not matches:
        matches = re.findall(r"-?\d[\d,]*(?:\.\d+)?", text)
    if not matches:
        return None
    try:
        return answer(matches[-1])
    except ValueError:
        return None


def pass_at_k(total, correct, k):
    if any(type(v) is not int for v in (total, correct, k)) or not 0 <= correct <= total or not 1 <= k <= total:
        raise ValueError("Invalid pass@k sample counts")
    return 1.0 if total - correct < k else 1 - math.comb(total - correct, k) / math.comb(total, k)


def sampled_metrics(predictions, expected, ks=(1, 16, 32)):
    if not predictions:
        raise ValueError("Sampled predictions are empty")
    counts = Counter(p for p in predictions if p is not None)
    # Stable lexicographic answer tie break, defined in the report.
    majority = min(counts, key=lambda p: (-counts[p], p)) if counts else None
    correct = sum(p == expected for p in predictions)
    return {
        "samples": len(predictions),
        "correct": correct,
        "passAtK": {str(k): pass_at_k(len(predictions), correct, k) for k in ks},
        "majorityAnswer": majority,
        "majorityCorrect": majority == expected,
    }


def generate_rows(
    model, tokenizer, rows, evaluation, chunk=16, *, sample=False, seed=11, temperature=0.6, count_tokens=False
):
    import torch

    if type(chunk) is not int or chunk < 1:
        raise ValueError("Invalid decoding chunk")
    from heteroes.v3.options import validate_prompt_format

    prompt_format = validate_prompt_format(evaluation.get("promptFormat"), evaluation["systemPrompt"])
    decoder = evaluation.get("decoder", "hf_generate")  # Recipe v2 always, v3 by choice
    from heteroes.catalog import CPU_GUARD_DECODER, STRICT_B22_DECODER, V3_DECODE_ENGINES

    if decoder not in V3_DECODE_ENGINES:
        raise ValueError("Unknown decoder")
    if decoder in (CPU_GUARD_DECODER, STRICT_B22_DECODER) and sample:
        raise ValueError(f"The {decoder} decoder is greedy only")
    if decoder in ("hf_compact", STRICT_B22_DECODER):
        if sample:
            raise ValueError("The compacting decoder is greedy only")
        from heteroes.eval import compact_decode

        # refuses a generation config it does not reproduce before anything is decoded
        eos_ids, pad_id, processors = compact_decode.decode_settings(
            model, evaluation["maxNewTokens"], tokenizer.pad_token_id
        )
    device = next(model.parameters()).device
    previous = tokenizer.padding_side
    tokenizer.padding_side = "left"
    output = []
    try:
        for offset in range(0, len(rows), chunk):
            group = rows[offset : offset + chunk]
            # Recipe v3 may have no system prompt (null): then only the user turn is sent
            system = (
                []
                if evaluation["systemPrompt"] is None
                else [{"role": "system", "content": evaluation["systemPrompt"]}]
            )
            prompts = (
                [r["prompt"] for r in group]
                if prompt_format == "raw"
                else [
                    tokenizer.apply_chat_template(
                        [*system, {"role": "user", "content": r["prompt"]}],
                        tokenize=False,
                        add_generation_prompt=True,
                    )
                    for r in group
                ]
            )
            inputs = {k: v.to(device) for k, v in tokenizer(prompts, return_tensors="pt", padding=True).items()}
            devices = [device.index or 0] if device.type == "cuda" else []
            if decoder == "hf_compact":
                new, _ = compact_decode.compact_generate_ids(
                    model,
                    inputs["input_ids"],
                    inputs["attention_mask"],
                    evaluation["maxNewTokens"],
                    eos_ids,
                    pad_id,
                    processors,
                )
            elif decoder == STRICT_B22_DECODER:
                from heteroes.eval import strict_backend

                new = strict_backend.generate_ids(
                    model,
                    inputs["input_ids"],
                    inputs["attention_mask"],
                    evaluation["maxNewTokens"],
                    eos_ids,
                    pad_id,
                    processors,
                )
            elif decoder == CPU_GUARD_DECODER:
                from heteroes.eval.cpu_guard import guarded_generate_ids

                ids, _ = guarded_generate_ids(model, **inputs, max_new_tokens=evaluation["maxNewTokens"])
                new = ids[:, inputs["input_ids"].shape[1] :]
            else:
                with torch.random.fork_rng(devices=devices), torch.no_grad():
                    torch.manual_seed(seed + offset)
                    options = {"temperature": temperature} if sample else {}
                    ids = model.generate(
                        **inputs, max_new_tokens=evaluation["maxNewTokens"], do_sample=sample, **options
                    )
                new = ids[:, inputs["input_ids"].shape[1] :]
            from heteroes import progress

            progress.advance("rollout")  # one generate() chunk finished (D11 stage progress)
            texts = tokenizer.batch_decode(new, skip_special_tokens=True)
            eos = model.generation_config.eos_token_id
            eos_ids = {eos} if isinstance(eos, int) else set(eos or [])
            for row, text, tokens in zip(group, texts, new, strict=True):
                prediction = extract(text)
                truncated = len(tokens) >= evaluation["maxNewTokens"] and not any(int(t) in eos_ids for t in tokens)
                output.append(
                    {
                        "prompt": row["prompt"],
                        "expected": row.get("answer"),  # Recipe v3 rows may have no answer: scored on the coordinator
                        "output": text,
                        "prediction": prediction,
                        "correct": row.get("answer") is not None and prediction == row["answer"],
                        "parseError": prediction is None,
                        "truncated": truncated,
                    }
                )
                if count_tokens:
                    from heteroes.v3.usage import generated_token_count

                    output[-1]["generatedTokens"] = generated_token_count(tokens.detach().cpu().tolist(), eos_ids)
    finally:
        tokenizer.padding_side = previous
    return output


def evaluate(model, tokenizer, rows, evaluation, chunk=16, *, count_tokens=False):
    if not rows:
        raise ValueError("Cannot evaluate an empty split")
    raw = generate_rows(model, tokenizer, rows, evaluation, chunk, **({"count_tokens": True} if count_tokens else {}))
    return {
        "accuracy": sum(r["correct"] for r in raw) / len(raw),
        "rows": raw,
        "count": len(raw),
        "parseErrors": sum(r["parseError"] for r in raw),
        "truncations": sum(r["truncated"] for r in raw),
        "rowsHash": sha(rows),
        "decoder": "greedy",
        "evaluation": evaluation,
    }
