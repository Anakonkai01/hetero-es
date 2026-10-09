"""
The compacting greedy decoder: the same answers as `model.generate(..., do_sample=False)`, without computing the answers that have already finished.

Why: `generate()` stops a batch only when EVERY answer in it has ended, so an answer that is finished keeps being computed (as padding) until the longest one of its batch
ends. On the workload `cot_l1_q128` only 44 percent of the token slots of a chunk of 64 held a real token (`artifacts/experiments/2026-10-09-rollout-waste/`); the time of a decoding
step grows with the batch, so those slots cost time. `compact_generate_ids` does the greedy decoding by hand and, every time at least `DROP_FRACTION` of the rows in
the batch have ended, removes them from the input, the attention mask and the key/value cache.

What it reproduces, exactly as the library does: left-padded prompts, the position ids taken from the attention mask, the logits processors that the model's generation config
asks for in greedy mode, the end tokens (all of the generation config's), padding after the end of an answer. It supports ONLY the repetition penalty (the one processor the project's
model uses); any other processor, and a key/value cache that cannot select rows, are not guessed: the first raises `UnsupportedDecode` before anything is decoded, the second makes
the decoder carry on WITHOUT removing rows (still correct, no speed-up; `stats["compaction_supported"]` says so).

What is measured and what is not (`artifacts/experiments/2026-10-09-compact-decode/`): its texts equal those of `generate()` in every comparison on FP32 (3 GPUs of 2 models, 3 model families, 4 tasks), except one
answer of 768 on one task whose two best tokens were 5.7e-6 apart, a tie that `generate()` itself breaks differently at another chunk size. This is NOT a guarantee of equal texts: no batch
shape change is (numerical contract section 17). The constants below are part of the engine: changing one changes which batch shapes occur, so it would need a new engine name.
"""
import copy

import torch

DROP_FRACTION = 0.1                 # rows are removed when at least this fraction of the rows still in the batch has ended (0.0 to 0.25 gave the same speed within 4 percent)
SUPPORTED_PROCESSORS = ("RepetitionPenaltyLogitsProcessor",)


class UnsupportedDecode(RuntimeError):
    """The model's generation settings ask for something this decoder does not reproduce."""


def decode_settings(model, max_new_tokens: int, tokenizer_pad_id: int | None = None):
    """
    (end token ids, padding id, logits processors) of greedy decoding for this model, as the library builds them from the generation config.
    Raises `UnsupportedDecode` if a processor other than the repetition penalty is active, or if the library no longer offers the way to build them.
    """
    config = copy.deepcopy(model.generation_config)
    config.do_sample = False
    config.max_new_tokens = max_new_tokens
    try:
        processors = model._get_logits_processor(config, 1, None, None, [])
    except Exception as error:                              # noqa: BLE001 - a private method of the library: say plainly if it moved
        raise UnsupportedDecode(f"cannot build the logits processors of the generation config ({type(error).__name__}: {error})") from error
    names = [type(processor).__name__ for processor in processors]
    unknown = [name for name in names if name not in SUPPORTED_PROCESSORS]
    if unknown:
        raise UnsupportedDecode(f"the generation config activates logits processors that the compacting decoder does not reproduce: {unknown}")
    eos = config.eos_token_id
    eos_ids = [] if eos is None else (list(eos) if isinstance(eos, (list, tuple)) else [eos])
    if not eos_ids:
        raise UnsupportedDecode("the generation config has no end token")
    pad = config.pad_token_id if config.pad_token_id is not None else (tokenizer_pad_id if tokenizer_pad_id is not None else eos_ids[0])
    return eos_ids, pad, processors


def position_ids_from_mask(attention_mask):
    """The position ids that `generate()` derives from a left-padded mask: 0, 1, 2, ... counted from the first real token; 0 under the padding."""
    return (attention_mask.long().cumsum(-1) - 1).masked_fill(attention_mask == 0, 0)


def compact_generate_ids(model, input_ids, attention_mask, max_new_tokens: int, eos_ids, pad_id: int, processors):
    """
    Greedy decoding of one batch of LEFT-padded prompts. Returns (tokens, stats): `tokens` is a (batch, max_new_tokens) tensor of the generated ids, the end token included and
    `pad_id` after it, like the new part of `generate()`'s output; `stats` has "steps", "slot_steps" (the sum over the steps of the rows computed), "compactions" and
    "compaction_supported".
    """
    device = input_ids.device
    batch = input_ids.shape[0]
    eos_t = torch.tensor(list(eos_ids), device=device)
    position = position_ids_from_mask(attention_mask)
    out = torch.full((batch, max_new_tokens), pad_id, dtype=torch.long, device=device)
    rows = torch.arange(batch, device=device)                       # original index of every row still in the batch
    stats = {"steps": 0, "slot_steps": 0, "compactions": 0, "compaction_supported": True}
    mask, all_ids, last_position = attention_mask, input_ids, position[:, -1]
    with torch.no_grad():
        result = model(input_ids=input_ids, attention_mask=attention_mask, position_ids=position, use_cache=True, logits_to_keep=1)
        cache = result.past_key_values
        scores = result.logits[:, -1].to(dtype=torch.float32)
        finished = torch.zeros(batch, dtype=torch.bool, device=device)
        for step in range(max_new_tokens):
            stats["steps"] += 1
            stats["slot_steps"] += int(rows.shape[0])
            scores = processors(all_ids, scores)
            next_tokens = torch.argmax(scores, dim=-1)
            next_tokens = torch.where(finished, torch.full_like(next_tokens, pad_id), next_tokens)      # a row that has ended gets padding, like the library
            out[rows, step] = next_tokens
            finished = finished | torch.isin(next_tokens, eos_t)
            if step == max_new_tokens - 1:
                break
            ended = int(finished.sum())
            if ended == rows.shape[0]:
                break
            if stats["compaction_supported"] and ended > 0 and ended >= max(1, DROP_FRACTION * rows.shape[0]):
                keep = torch.nonzero(~finished).squeeze(1)
                try:
                    cache.batch_select_indices(keep)
                except Exception:                                   # noqa: BLE001 - a cache that cannot select rows: go on without removing any
                    stats["compaction_supported"] = False
                else:
                    rows, mask, all_ids, last_position = rows[keep], mask[keep], all_ids[keep], last_position[keep]
                    next_tokens = next_tokens[keep]
                    finished = torch.zeros(rows.shape[0], dtype=torch.bool, device=device)
                    stats["compactions"] += 1
            all_ids = torch.cat([all_ids, next_tokens[:, None]], dim=-1)
            mask = torch.cat([mask, mask.new_ones((mask.shape[0], 1))], dim=-1)
            last_position = last_position + 1
            result = model(input_ids=next_tokens[:, None], attention_mask=mask, position_ids=last_position[:, None], past_key_values=cache, use_cache=True)
            cache = result.past_key_values
            scores = result.logits[:, -1].to(dtype=torch.float32)
    return out, stats
