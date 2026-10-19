from dataclasses import dataclass

import torch

from heteroes.eval.workload import (
    DO_SAMPLE,
    EXAMPLES,
    MAX_NEW_TOKENS,
    SYSTEM_PROMPT,
    exact_match_reward,
    extract_integer,
)


@dataclass(frozen=True)
class EvalRecord:
    """What happened for one question. The full text is kept so that a wrong prediction can be debugged."""
    question: str
    expected: int
    output_text: str
    prediction: int | None
    reward: float


@dataclass(frozen=True)
class EvalResult:
    mean_reward: float
    records: tuple[EvalRecord, ...]


def generate_answer(model, tokenizer, question: str) -> str:
    """
    Ask the model ONE question and return its answer as text (stripped).

    Greedy decoding (do_sample=False) with the token budget of the workload, one prompt at a time, so there is
    no padding. Note that the model's own generation_config (repetition_penalty and so on) still applies:
    it belongs to the checkpoint, so record it with the results.
    """
    device = next(model.parameters()).device

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": question},
    ]
    inputs = tokenizer.apply_chat_template(
        messages,
        return_tensors="pt",
        return_dict=True,
        add_generation_prompt=True,  # open the assistant turn, so the model answers instead of continuing the question
        tokenize=True,
    )
    inputs = {key: value.to(device) for key, value in inputs.items()}

    with torch.no_grad():
        output_ids = model.generate(**inputs, max_new_tokens=MAX_NEW_TOKENS, do_sample=DO_SAMPLE)

    # generate() returns the prompt followed by the answer: keep only the new tokens
    prompt_length = inputs["input_ids"].shape[1]
    answer = tokenizer.batch_decode(output_ids[:, prompt_length:], skip_special_tokens=True)[0]

    return answer.strip()


def generate_answers(model, tokenizer, questions: list[str]) -> list[str]:
    """
    Ask several questions in ONE generate() call (left padding) and return the answers in the same order.

    This is the "chunk" of MASTER: the prompt set stays whole, only the number of prompts per call changes. Padding can change
    the numbers the model computes, so a chunk size is usable only if its answers are the same as one prompt at a time
    (`heteroes.profile` checks that); this function does not promise it.
    """
    device = next(model.parameters()).device
    texts = [tokenizer.apply_chat_template(
        [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": question}],
        tokenize=False, add_generation_prompt=True) for question in questions]
    previous_side = tokenizer.padding_side
    tokenizer.padding_side = "left"
    try:
        inputs = tokenizer(texts, return_tensors="pt", padding=True)
    finally:
        tokenizer.padding_side = previous_side
    inputs = {key: value.to(device) for key, value in inputs.items()}
    with torch.no_grad():
        output_ids = model.generate(**inputs, max_new_tokens=MAX_NEW_TOKENS, do_sample=DO_SAMPLE)
    prompt_length = inputs["input_ids"].shape[1]
    return [text.strip() for text in tokenizer.batch_decode(output_ids[:, prompt_length:], skip_special_tokens=True)]


def evaluate_model(model, tokenizer, chunk: int = 1) -> EvalResult:
    """
    Run the 16 questions of the workload and score them. `chunk` prompts go into one generate() call (1 = one at a time, the
    reference behaviour; the questions and their order never change, only how they are grouped).

    A failure while generating (for example CUDA out of memory) is raised, never turned into a reward of 0:
    an infrastructure failure is not a wrong answer. An answer without any integer is a wrong answer.
    """
    if isinstance(chunk, bool) or not isinstance(chunk, int) or chunk < 1:
        raise ValueError(f"chunk must be an integer of at least 1, got {chunk!r}")
    records = []
    for start in range(0, len(EXAMPLES), chunk):
        group = EXAMPLES[start:start + chunk]
        # looked up in this module at call time, so that tests can replace them
        if chunk == 1:
            texts = [generate_answer(model, tokenizer, group[0].question)]
        else:
            texts = generate_answers(model, tokenizer, [example.question for example in group])
        for example, output_text in zip(group, texts):
            prediction = extract_integer(output_text)
            reward = exact_match_reward(prediction, example.answer)
            records.append(EvalRecord(example.question, example.answer, output_text, prediction, reward))

    return EvalResult(sum(r.reward for r in records) / len(records), tuple(records))
