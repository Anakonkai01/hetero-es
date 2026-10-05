import re
from dataclasses import dataclass

from heteroes.canonical import canonical_json_hash


# The 16-prompt arithmetic workload of the probe of 2026-09-29 (artifacts/probes/2026-09-29), moved here so
# that every machine, worker and coordinator read ONE definition. Its hash is recorded by the probe.
SYSTEM_PROMPT = "You are a calculator. Answer with only with number"
MAX_NEW_TOKENS = 16
DO_SAMPLE = False
REWARD_TYPE = "exact_integer_match"


@dataclass(frozen=True)
class Example:
    question: str
    answer: int


# a tuple of frozen objects: nobody can change the workload by accident after import
EXAMPLES: tuple[Example, ...] = (
    Example("What is 17 + 24?", 41),
    Example("What is 6 * 8?", 48),
    Example("What is 91 - 37?", 54),
    Example("What is 12 * 13?", 156),
    Example("What is 137 * 46?", 6302),
    Example("What is 375 + 918 - 427?", 866),
    Example("What is 23 * 17 + 48?", 439),
    Example("What is (144 / 12) * 37?", 444),
    Example("What is 218 * 37?", 8066),
    Example("What is 84 * 19 - 76?", 1520),
    Example("What is 312 * 27 - 145?", 8279),
    Example("What is (73 + 29) * 18?", 1836),
    Example(
        "A shop has 48 boxes with 36 pens in each box. It sells 725 pens. How many pens remain?",
        1003,
    ),
    Example(
        "A school buys 36 packs of notebooks with 24 notebooks per pack. "
        "It distributes 579 notebooks. How many remain?",
        285,
    ),
    Example(
        "A train travels 72 km per hour for 5 hours, then another 148 km. What is the total distance?",
        508,
    ),
    Example(
        "A factory makes 125 items per hour for 18 hours. "
        "347 items are defective. How many usable items remain?",
        1903,
    ),
)


def workload_dict() -> dict:
    """
    The workload as plain data, in the exact shape the probe hashed:
    system prompt, token budget, sampling flag, reward type and the examples.
    """
    return {
        "system_prompt": SYSTEM_PROMPT,
        "max_new_tokens": MAX_NEW_TOKENS,
        "do_sample": DO_SAMPLE,
        "reward_type": REWARD_TYPE,
        "examples": [{"question": e.question, "answer": e.answer} for e in EXAMPLES],
    }


def workload_hash() -> str:
    """Fingerprint of the workload. Equal hashes mean two machines ask the same questions the same way."""
    return canonical_json_hash(workload_dict())


def extract_integer(text: str) -> int | None:
    """
    The prediction: the LAST integer in the model's text, or None if there is none.

    Behaves exactly like the probe, so that the predictions recorded on 2026-09-29 stay comparable:
    commas are dropped first ("1,003" is 1003), and the pattern is "-?digits", so "5-3" gives -3
    and "3.5" gives 5. These are quirks kept on purpose, not features.
    """
    numbers = re.findall(r"-?\d+", text.replace(",", ""))
    if not numbers:
        return None
    return int(numbers[-1])


def exact_match_reward(prediction: int | None, expected: int) -> float:
    """1.0 if the prediction equals the expected integer, else 0.0 (also when there is no prediction)."""
    return 1.0 if prediction == expected else 0.0
