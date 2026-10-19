"""
Helpers of the second learning experiment (experiment code): the workload is `cot_l1_q128` (level 1: two-digit operations, short replies, no 256-token cut), the held-out sets, the token
limit used to evaluate them, the choice of a checkpoint on a validation set and the criteria of `PREREGISTRATION.md`. Reuses `learnlib` of the first experiment for what did not change.
"""
import contextlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "2026-10-07-learning-runtime"))
import learnlib  # noqa: E402,F401  (summarize, evaluate_questions, keep_checkpoint, CheckpointKeeper, sign_test_p, dump)
import heteroes.eval.cot_workload as cot  # noqa: E402
from heteroes.eval.cot_workload import make_questions  # noqa: E402
from learnlib import CheckpointKeeper, dump, evaluate_questions, keep_checkpoint, sign_test_p, summarize  # noqa: E402,F401

TRAIN_LEVEL, TRAIN_COUNT = 1, 128
# name: (level, count, generator seed). H1: test set of the training family; V1: validation set of the same family (it chooses the checkpoint); H2, H3: other families (collateral damage).
SETS = {"H1": (1, 256, 20261008), "V1": (1, 256, 20261009), "H2": (2, 128, 20261008), "H3": (3, 128, 20261008)}
SEEDS = {name: seed for name, (_, _, seed) in SETS.items()}
HELDOUT_TOKEN_LIMIT = 512          # the level-3 replies are cut at 256 (artifacts/experiments/2026-10-08-uncut-probe): the held-out sets are evaluated with room to finish
TRAIN_TOKEN_LIMIT = 256            # the training questions are evaluated as the workload does it


def train_questions() -> list[tuple[str, int]]:
    """The questions the candidates are scored on: exactly those of the workload `cot_l1_q128`."""
    return make_questions(TRAIN_COUNT, TRAIN_LEVEL)


def heldout_sets() -> dict[str, list[tuple[str, int]]]:
    """
    The held-out sets with their sizes. A question that is a training question, or one of a set made before it, is dropped and the next one of the generator takes its place:
    level 1 has only about 24,000 different questions, so two random sets of 256 share a few by chance, and the validation set must not leak into the test set.
    """
    forbidden = {question for question, _ in train_questions()}
    sets = {}
    for name, (level, count, seed) in SETS.items():
        pool = make_questions(count + len(forbidden) + sum(len(s) for s in sets.values()), level, seed)
        chosen = [(question, answer) for question, answer in pool if question not in forbidden][:count]
        if len(chosen) != count:
            raise RuntimeError(f"{name}: only {len(chosen)} questions left after removing the used ones")
        sets[name] = chosen
        forbidden |= {question for question, _ in chosen}
    return sets


@contextlib.contextmanager
def token_limit(limit: int):
    """The reply limit of `heteroes.eval.cot_workload.generate`, for the block (restored even after an error)."""
    previous = cot.MAX_NEW_TOKENS
    cot.MAX_NEW_TOKENS = limit
    try:
        yield
    finally:
        cot.MAX_NEW_TOKENS = previous


def select_checkpoint(validation: dict[int, float]) -> int:
    """The generation (not the base, generation 0) with the best validation accuracy; the earliest one on a tie (the less trained model is the safer choice)."""
    candidates = {g: a for g, a in validation.items() if g > 0}
    if not candidates:
        raise ValueError("no checkpoint after the base")
    best = max(candidates.values())
    return min(g for g, a in candidates.items() if a == best)


def verdict(base: dict, selected: dict, non_tie_pos: int, non_tie_neg: int, last3_mean: dict, walks_lower: list[bool]) -> dict:
    """
    The criteria of PREREGISTRATION.md of the second experiment. `base` and `selected` hold summaries ("train", "H1", "H2", "H3" with an "accuracy");
    `last3_mean` the mean accuracy of H2 and H3 over the last three checkpoints; `walks_lower` one boolean per shuffled walk: did it end below the real trajectory?
    """
    eps = 1e-12
    p1 = selected["H1"]["accuracy"] - base["H1"]["accuracy"] >= 0.06 - eps
    non_ties = non_tie_pos + non_tie_neg
    p2 = (non_ties >= 20 and non_tie_pos / non_ties >= 0.60 and sign_test_p(non_tie_pos, non_tie_neg) <= 0.05
          and len(walks_lower) > 0 and all(walks_lower))
    p3 = selected["train"]["accuracy"] - base["train"]["accuracy"] >= 0.08 - eps
    p4 = all(last3_mean[k] - base[k]["accuracy"] >= -0.06 - eps for k in ("H2", "H3"))
    if p1 and p2 and p3 and p4:
        label = "ES improved held-out accuracy on this workload (not limited by the token cut)"
    elif p1 and p3 and p4:
        label = "held-out accuracy improved but the direction of the update was not shown to matter"
    else:
        label = "no evidence of improvement on held-out arithmetic in this experiment"
    return {"P1": p1, "P2": p2, "P3": p3, "P4": p4, "label": label}
