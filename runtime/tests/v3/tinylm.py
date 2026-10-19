"""A tiny causal LM with its own byte-level BPE tokenizer and chat template, built offline in a directory (test helper)."""

import json

CHAT_TEMPLATE = (
    "{% for m in messages %}<|im_start|>{{ m['role'] }}\n{{ m['content'] }}<|im_end|>\n{% endfor %}"
    "{% if add_generation_prompt %}<|im_start|>assistant\n{% endif %}"
)


def build_tiny_lm(directory, seed=0):
    import torch
    import transformers
    from tokenizers import Tokenizer, decoders, models, pre_tokenizers, trainers

    tokenizer = Tokenizer(models.BPE())
    tokenizer.pre_tokenizer = pre_tokenizers.ByteLevel(add_prefix_space=False)
    tokenizer.decoder = decoders.ByteLevel()
    trainer = trainers.BpeTrainer(
        vocab_size=300,
        special_tokens=["<|endoftext|>", "<|im_start|>", "<|im_end|>"],
        initial_alphabet=pre_tokenizers.ByteLevel.alphabet(),
    )
    tokenizer.train_from_iterator(["What is 17 plus 24? Answer: 41", "Solve the problem step by step."] * 10, trainer)
    fast = transformers.PreTrainedTokenizerFast(
        tokenizer_object=tokenizer, eos_token="<|im_end|>", pad_token="<|endoftext|>"
    )
    fast.chat_template = CHAT_TEMPLATE
    config = transformers.Qwen2Config(
        vocab_size=len(fast),
        hidden_size=32,
        intermediate_size=64,
        num_hidden_layers=2,
        num_attention_heads=4,
        num_key_value_heads=2,
        max_position_embeddings=256,
        tie_word_embeddings=True,
        eos_token_id=fast.eos_token_id,
        pad_token_id=fast.pad_token_id,
    )
    torch.manual_seed(seed)
    model = transformers.Qwen2ForCausalLM(config).half()
    model.generation_config.eos_token_id = fast.eos_token_id
    model.generation_config.pad_token_id = fast.pad_token_id
    model.save_pretrained(directory, safe_serialization=True)
    fast.save_pretrained(directory)
    return directory


def write_rows(path, count=20):
    rows = [{"question": f"What is {i} plus {i}?", "answer": str(2 * i), "level": i % 3} for i in range(count)]
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")
    return path
