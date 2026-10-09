"""
`heteroes.eval.compact_decode`: the compacting greedy decoder gives the ids that `model.generate(..., do_sample=False)` gives.

A tiny Qwen2 model with random weights on the CPU (FP32), left-padded prompts of different lengths and end tokens chosen from what the model really generates, so that the rows of a batch
end at different steps (a premise check makes sure of it: without staggered ends nothing would be compacted and the tests would prove nothing).
"""
import copy

import pytest
import torch
from transformers import DynamicCache, Qwen2Config, Qwen2ForCausalLM

from heteroes.eval import compact_decode as cd

PAD = 0
NEVER = 99
LENGTHS = [5, 3, 7, 4, 6, 2, 8, 5, 4, 6, 3, 7]
NEW = 30


def tiny_model(repetition_penalty=None):
    torch.manual_seed(1234)
    config = Qwen2Config(vocab_size=64, hidden_size=32, intermediate_size=64, num_hidden_layers=2, num_attention_heads=4, num_key_value_heads=2,
                         max_position_embeddings=256, tie_word_embeddings=False, initializer_range=0.4)
    model = Qwen2ForCausalLM(config).float().eval()
    model.generation_config.pad_token_id = PAD
    model.generation_config.do_sample = False
    if repetition_penalty is not None:
        model.generation_config.repetition_penalty = repetition_penalty
    return model


def left_padded(lengths=LENGTHS, seed=7):
    generator = torch.Generator().manual_seed(seed)
    width = max(lengths)
    ids = torch.full((len(lengths), width), PAD, dtype=torch.long)
    mask = torch.zeros((len(lengths), width), dtype=torch.long)
    for row, length in enumerate(lengths):
        ids[row, width - length:] = torch.randint(2, 63, (length,), generator=generator)
        mask[row, width - length:] = 1
    return ids, mask


def library_new_tokens(model, ids, mask, eos):
    model.generation_config.eos_token_id = eos
    with torch.no_grad():
        out = model.generate(input_ids=ids, attention_mask=mask, max_new_tokens=NEW, do_sample=False, pad_token_id=PAD)
    return out[:, ids.shape[1]:]


def staggered_eos(model, ids, mask):
    """End tokens taken from the sequences the model really generates, at different positions, so that the rows end at different steps."""
    free = library_new_tokens(model, ids, mask, [NEVER])           # an id outside the vocabulary: nothing ends, whole sequences are seen
    eos = sorted({int(free[0, 3]), int(free[1, 6]), int(free[2, 9])})
    return eos


def end_steps(new, eos):
    steps = []
    for row in new:
        hits = [i for i, token in enumerate(row.tolist()) if token in eos]
        steps.append(hits[0] if hits else None)
    return steps


def run_both(repetition_penalty=None):
    model = tiny_model(repetition_penalty)
    ids, mask = left_padded()
    eos = staggered_eos(model, ids, mask)
    reference = library_new_tokens(model, ids, mask, eos)
    steps = end_steps(reference, eos)
    ended = [s for s in steps if s is not None]
    assert len(set(ended)) >= 3, f"premise: the rows must end at different steps, got {steps}"
    eos_ids, pad, processors = cd.decode_settings(model, NEW)
    assert eos_ids == eos and pad == PAD
    tokens, stats = cd.compact_generate_ids(model, ids, mask, NEW, eos_ids, pad, processors)
    return reference, tokens, stats, steps


def test_same_ids_as_generate_when_the_rows_end_at_different_steps():
    reference, tokens, stats, _ = run_both()
    width = reference.shape[1]
    assert torch.equal(tokens[:, :width], reference)
    assert bool((tokens[:, width:] == PAD).all())             # the library stops early when every row has ended: the rest is padding


def test_same_ids_with_the_repetition_penalty_of_the_generation_config():
    plain_reference, plain_tokens, _, _ = run_both()
    reference, tokens, stats, _ = run_both(repetition_penalty=1.8)
    width = reference.shape[1]
    assert torch.equal(tokens[:, :width], reference)


def test_the_penalty_really_changes_the_answers_in_this_setup():
    # premise of the test above: if the penalty changed nothing, a decoder that ignored it would pass too
    _, tokens_plain, _, _ = run_both()
    _, tokens_penalty, _, _ = run_both(repetition_penalty=1.8)
    assert not torch.equal(tokens_plain, tokens_penalty)


def test_rows_are_removed_and_work_is_saved():
    _, _, stats, steps = run_both()
    assert stats["compactions"] >= 1 and stats["compaction_supported"] is True
    assert stats["slot_steps"] < stats["steps"] * len(LENGTHS)       # fewer rows computed than a batch that never shrinks


def test_a_cache_that_cannot_select_rows_still_gives_the_same_ids(monkeypatch):
    def refuse(self, indices):
        raise NotImplementedError("no row selection in this cache")
    monkeypatch.setattr(DynamicCache, "batch_select_indices", refuse)
    reference, tokens, stats, _ = run_both()
    assert torch.equal(tokens[:, : reference.shape[1]], reference)
    assert stats["compaction_supported"] is False and stats["compactions"] == 0


def test_an_unsupported_logits_processor_is_refused_before_decoding():
    model = tiny_model()
    model.generation_config.no_repeat_ngram_size = 2
    with pytest.raises(cd.UnsupportedDecode, match="NoRepeatNGram"):
        cd.decode_settings(model, NEW)


def test_no_end_token_is_refused():
    model = tiny_model()
    model.generation_config.eos_token_id = None
    with pytest.raises(cd.UnsupportedDecode, match="end token"):
        cd.decode_settings(model, NEW)


def test_the_padding_id_falls_back_to_the_tokenizer_then_to_the_first_end_token():
    model = tiny_model()
    model.generation_config.eos_token_id = [5, 6]
    model.generation_config.pad_token_id = None
    assert cd.decode_settings(model, NEW, tokenizer_pad_id=9)[1] == 9
    assert cd.decode_settings(model, NEW)[1] == 5


def test_a_single_row_equals_the_library_too():
    model = tiny_model()
    ids, mask = left_padded([6])
    eos = [int(library_new_tokens(model, ids, mask, [NEVER])[0, 4])]
    reference = library_new_tokens(model, ids, mask, eos)
    eos_ids, pad, processors = cd.decode_settings(model, NEW)
    tokens, stats = cd.compact_generate_ids(model, ids, mask, NEW, eos_ids, pad, processors)
    assert torch.equal(tokens[:, : reference.shape[1]], reference)
    assert stats["steps"] == reference.shape[1]


def test_position_ids_count_from_the_first_real_token_of_each_row():
    # With rotary embeddings a constant shift of a row's positions cancels in exact arithmetic, so the generated ids alone cannot show a wrong offset: the function is checked on its own.
    mask = torch.tensor([[0, 0, 1, 1, 1], [1, 1, 1, 1, 1], [0, 1, 1, 1, 1], [0, 0, 0, 0, 1]])
    expected = torch.tensor([[0, 0, 0, 1, 2], [0, 1, 2, 3, 4], [0, 0, 1, 2, 3], [0, 0, 0, 0, 0]])
    assert torch.equal(cd.position_ids_from_mask(mask), expected)
    assert cd.position_ids_from_mask(mask).dtype == torch.long


def test_the_first_decoding_step_uses_the_position_after_the_last_real_token():
    # a row with 2 real tokens (mask 0 0 1 1) is at position 1 after its prompt, so its first generated token sits at position 2
    mask = torch.tensor([[0, 0, 1, 1]])
    assert int(cd.position_ids_from_mask(mask)[:, -1]) + 1 == 2
