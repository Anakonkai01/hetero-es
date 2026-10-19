"""
Helpers of the learning experiment (experiment code, not package code): the held-out sets, the evaluation with its decomposition, the rule that
chooses which checkpoints are kept, and the arithmetic of the criteria. Pure functions where possible, so that `tests/experiments/test_learnlib.py` can test them.
"""
import json
import math

from heteroes.eval.cot_workload import extract_answer, generate, make_questions

HELDOUT_SEED = 20261008
HELDOUT_COUNT = 128
TRAIN_COUNT = 64
TRAIN_LEVEL = 3
HELDOUT_LEVELS = {"H3": 3, "H1": 1, "H2": 2}      # H3: the training family; H1 and H2: other families
EVAL_CHUNK = 64


def train_questions() -> list[tuple[str, int]]:
    """The questions the candidates are scored on: exactly those of the workload `cot_l3_q64`."""
    return make_questions(TRAIN_COUNT, TRAIN_LEVEL)


def heldout_sets(count: int = HELDOUT_COUNT, seed: int = HELDOUT_SEED) -> dict[str, list[tuple[str, int]]]:
    """
    The three held-out sets. A question that is also a training question is removed (it can only happen at level 3: the word problems have few numbers) and replaced
    by the next question of the generator, so every set has exactly `count` questions and none is a training question.
    """
    forbidden = {question for question, _ in train_questions()}
    sets = {}
    for name, level in HELDOUT_LEVELS.items():
        pool = make_questions(count + len(forbidden), level, seed)
        chosen = [(question, answer) for question, answer in pool if question not in forbidden][:count]
        if len(chosen) != count:
            raise RuntimeError(f"{name}: only {len(chosen)} questions left after removing the training ones")
        sets[name] = chosen
    return sets


def evaluate_questions(model, tokenizer, qa: list[tuple[str, int]], chunk: int = EVAL_CHUNK) -> dict:
    """Ask `qa` (greedy, the workload's prompt and limits) and return the per-question correctness and what is needed to say WHY the accuracy is what it is."""
    texts, tokens = generate(model, tokenizer, [question for question, _ in qa], chunk)
    correct, answer_line, chars = [], [], []
    for (question, answer), text in zip(qa, texts, strict=True):
        correct.append(extract_answer(text) == answer)
        answer_line.append("Answer:" in text)
        chars.append(len(text))
    return {"correct": correct, "answer_line": answer_line, "chars": chars, "tokens": tokens}


def summarize(evaluation: dict) -> dict:
    """Accuracy, the share of replies with an `Answer:` line, the accuracy among those, the mean length in characters."""
    n = len(evaluation["correct"])
    with_line = [c for c, a in zip(evaluation["correct"], evaluation["answer_line"], strict=True) if a]
    return {"n": n, "correct": sum(evaluation["correct"]), "accuracy": sum(evaluation["correct"]) / n,
            "answer_line_rate": sum(evaluation["answer_line"]) / n,
            "accuracy_with_line": (sum(with_line) / len(with_line)) if with_line else None,
            "mean_chars": sum(evaluation["chars"]) / n, "tokens": evaluation["tokens"]}


def keep_checkpoint(child_generation: int, total_generations: int, every: int) -> bool:
    """
    Keep the weights that generation `child_generation` produced (the parent of the next one)? The weights after generation g are "generation g+1": kept when
    g+1 is a multiple of `every`, and the last ones are always kept. The base weights (generation 0) are kept by the caller.
    """
    if every < 1 or total_generations < 1 or not 0 <= child_generation < total_generations:
        raise ValueError(f"bad checkpoint rule: {child_generation}, {total_generations}, {every}")
    return (child_generation + 1) % every == 0 or child_generation == total_generations - 1


def checkpoint_name(generation: int, sha256: str) -> str:
    return f"g{generation:03d}-{sha256}.bin"


def count_positive(differences: list[float]) -> int:
    return sum(1 for d in differences if d > 0)


def sign_test_p(positive: int, negative: int) -> float:
    """One-sided p-value of at least `positive` successes among positive+negative non-ties if each is 50/50 (exact binomial)."""
    n = positive + negative
    if n == 0:
        return 1.0
    return sum(math.comb(n, k) for k in range(positive, n + 1)) / 2 ** n


def verdict(base: dict, final: dict, s2_positive: int, s2_mean: float, generations: int) -> dict:
    """
    The criteria of PREREGISTRATION.md. `base` and `final` hold the summaries of the base and the final weights: keys "train", "H3", "H1", "H2".
    Thresholds in questions are turned into fractions of the set size (8/128).
    """
    margin = 8 / 128
    s1 = final["H3"]["accuracy"] - base["H3"]["accuracy"] >= margin - 1e-12
    s2 = s2_positive >= 0.7 * generations and s2_mean > 0
    s3 = final["train"]["accuracy"] - base["train"]["accuracy"] >= 0.10 - 1e-12
    s4 = all(base[k]["accuracy"] - final[k]["accuracy"] <= margin + 1e-12 for k in ("H1", "H2"))
    base_c, final_c = base["H3"]["accuracy_with_line"], final["H3"]["accuracy_with_line"]
    s5 = None if base_c is None or final_c is None else base_c - final_c <= 0.05 + 1e-12
    if s1 and s2 and s3 and s4:
        label = "a learning signal on this workload" + (" that is not explained by shorter replies alone" if s5 else "" if s5 is not None else "")
    elif s2 and not s1:
        label = "the direction carries information but the generations did not move held-out accuracy"
    else:
        label = "no evidence of learning in this experiment"
    return {"S1": s1, "S2": s2, "S3": s3, "S4": s4, "S5": s5, "label": label}


def dump(path, document) -> None:
    with open(path, "w", encoding="utf-8") as file:
        json.dump(document, file, indent=1)
        file.write("\n")


class CheckpointKeeper:
    """
    Keeps the weights worth keeping: reads the coordinator's `events.jsonl` as it grows and makes a hard link (a copy if the disk differs) of the published file
    `<sha>.bin` into the checkpoint directory, before the runtime's own pruning (it keeps the last 3 versions) deletes it. Call `poll()` every few seconds.
    A file that is not there yet stays pending and is tried again at the next poll.
    """

    def __init__(self, events_path, published_dir, ckpt_dir, total_generations: int, every: int):
        from pathlib import Path
        self.events_path, self.published, self.ckpt = Path(events_path), Path(published_dir), Path(ckpt_dir)
        self.total, self.every = total_generations, every
        self.offset = 0
        self.pending: list[tuple[int, str]] = []
        self.kept: dict[int, str] = {}
        self.finished = False                    # the last generation is done: a worker that exits now is not a dead worker
        self.ckpt.mkdir(parents=True, exist_ok=True)

    def _read_new_events(self) -> list[dict]:
        if not self.events_path.is_file():
            return []
        with open(self.events_path, "rb") as file:
            file.seek(self.offset)
            data = file.read()
        end = data.rfind(b"\n") + 1                       # a half-written last line waits for the next poll
        self.offset += end
        events = []
        for line in data[:end].splitlines():
            try:
                events.append(json.loads(line))
            except ValueError:
                continue
        return events

    def _want(self, generation: int, sha256: str) -> None:
        if generation not in self.kept and (generation, sha256) not in self.pending:
            self.pending.append((generation, sha256))

    def _link(self, generation: int, sha256: str) -> bool:
        import os
        import shutil
        source, target = self.published / f"{sha256}.bin", self.ckpt / checkpoint_name(generation, sha256)
        if not source.is_file():
            return False
        if not target.exists():
            try:
                os.link(source, target)
            except OSError:
                shutil.copyfile(source, target)
        return True

    def poll(self) -> None:
        for event in self._read_new_events():
            if event.get("event") == "listening":
                self._want(0, event["initial_weights_sha256"])
            elif event.get("event") == "generation_done" and event.get("generation") == self.total - 1:
                self.finished = True
            elif event.get("event") == "weights_published" and keep_checkpoint(event["generation"], self.total, self.every):
                self._want(event["generation"] + 1, event["child_sha256"])
        still = []
        for generation, sha256 in self.pending:
            if self._link(generation, sha256):
                self.kept[generation] = sha256
            else:
                still.append((generation, sha256))
        self.pending = still
