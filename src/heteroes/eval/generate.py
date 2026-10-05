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


def evaluate_model(model, tokenizer) -> EvalResult:
    """
    Run the 16 questions of the workload and score them.

    A failure while generating (for example CUDA out of memory) is raised, never turned into a reward of 0:
    an infrastructure failure is not a wrong answer. An answer without any integer is a wrong answer.
    """
    records = []
    for example in EXAMPLES:
        # looked up in this module at call time, so that tests can replace it
        output_text = generate_answer(model, tokenizer, example.question)
        prediction = extract_integer(output_text)
        reward = exact_match_reward(prediction, example.answer)
        records.append(EvalRecord(example.question, example.answer, output_text, prediction, reward))

    return EvalResult(sum(r.reward for r in records) / len(records), tuple(records))
