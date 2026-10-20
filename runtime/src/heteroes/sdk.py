"""
The Python entry point for researchers (ADR-008, owner decision 8): configure an ES experiment, give it a reward, train.

    from heteroes.sdk import ESConfig, ESTrainer, reward

    @reward("keyword-hit@1")                    # name@version: part of the plan, with the SHA-256 of this file
    def keyword_hit(completions, rows):         # one score per row; the reward of a candidate is their mean
        return [float(row["keyword"] in text) for text, row in zip(completions, rows)]

    args = ESConfig(model_path="models/my-model", model_id="my-org/my-model", train_dataset="data.jsonl",
                    prompt_field="question", population=16, generations=50, sigma=1e-3, alpha=1e-3, batch_size=32)
    ESTrainer(args, reward_func=keyword_hit).train("runs/first", device="cuda")

A reward function must be a module-level function in a .py file: that file is hashed into the plan, so a changed reward is
a different experiment. A declarative scorer (`scorer={"name": "answer-line-last-number"}`) needs no code and is what a
shared lab accepts. The run happens on this machine with the lab's own coordinator, workers and protocol
(`heteroes.v3.local`); nothing is sent anywhere.
"""

import inspect
from dataclasses import dataclass, field


def reward(name_version: str):
    """Name and version a reward function: `@reward("my-reward@1")`."""
    name, _, version = name_version.partition("@")
    if not name or not version.isdigit() or int(version) < 1:
        raise ValueError("write the reward's identity as name@version, for example 'keyword-hit@1'")

    def mark(function):
        function.heteroes_scorer = (name, int(version))
        return function

    return mark


@dataclass
class ESConfig:
    model_path: str
    model_id: str
    train_dataset: str
    prompt_field: str = "prompt"
    population: int = 8
    generations: int = 10
    alpha: float = 1e-3
    sigma: float = 1e-3
    sigma_schedule: str = "constant"
    sigma_minimum: float | None = None
    antithetic: bool = False
    batch_size: int = 16
    batch_seed: int = 11
    split_seed: int = 42
    max_new_tokens: int = 256
    system_prompt: str | None = None
    eval_dtype: str = "float32"
    eval_chunk: int | None = None  # prompts per generate() call, fixed in the recipe (FP32: 16, 32 or 64); None: 16
    decoder: str = "hf_generate"
    noise_engine: str = "cpu"
    weight_space: dict = field(default_factory=lambda: {"kind": "full"})
    coefficient_rule: str = "zscore@1"  # or "centered-rank@1"; a Python rule is ESTrainer(coefficient_func=...)
    alpha_schedule: str = (
        "constant"  # "cosine" or "linear": from alpha at the first generation to alpha_minimum at the last
    )
    alpha_minimum: float | None = None
    momentum_beta: float | None = (
        None  # momentum over the last momentum_window generations (beta a float32, e.g. 0.875)
    )
    momentum_window: int = 4
    # "epoch-shuffle@1" walks the train split in shuffled epochs; the default draws an independent sample per generation
    sampler: str = "sha256-python-random-sample-v1"

    def to_config(self, scorer: dict) -> dict:
        """The configuration `heteroes.v3.local.run_local` and `python -m heteroes.v3 run` read."""
        return {
            "model": {"path": str(self.model_path), "id": self.model_id},
            "data": {
                "path": str(self.train_dataset),
                "promptField": self.prompt_field,
                "batchSize": self.batch_size,
                "batchSeed": self.batch_seed,
                "splitSeed": self.split_seed,
                "sampler": self.sampler,
            },
            "weightSpace": dict(self.weight_space),
            "noiseEngine": self.noise_engine,
            "sigma": {
                "kind": self.sigma_schedule,
                "initial": self.sigma,
                "minimum": self.sigma if self.sigma_minimum is None else self.sigma_minimum,
            },
            "antithetic": self.antithetic,
            "maxNewTokens": self.max_new_tokens,
            "systemPrompt": self.system_prompt,
            "evalDtype": self.eval_dtype,
            **({"evalChunk": self.eval_chunk} if self.eval_chunk is not None else {}),
            "decoder": self.decoder,
            "population": self.population,
            "generations": self.generations,
            "alpha": self.alpha,
            "coefficientRule": self.coefficient_rule,
            "scorer": scorer,
            **(
                {}
                if self.alpha_schedule == "constant" and self.alpha_minimum is None
                else {"alphaSchedule": {"kind": self.alpha_schedule, "minimum": self.alpha_minimum or self.alpha}}
            ),
            **(
                {}
                if self.momentum_beta is None
                else {"momentum": {"beta": self.momentum_beta, "window": self.momentum_window}}
            ),
        }


class ESTrainer:
    """Runs an `ESConfig` with a reward: a Python `reward_func` or a declarative `scorer` (exactly one of them)."""

    def __init__(self, args: ESConfig, reward_func=None, scorer: dict | None = None, coefficient_func=None):
        if (reward_func is None) == (scorer is None):
            raise ValueError("give either reward_func (Python) or scorer (declarative)")
        self.args = args
        # f(rewards) -> one coefficient per candidate, in a saved .py file like a reward function: pinned by its source
        self.coefficient_rule = None if coefficient_func is None else self._source(coefficient_func, "coefficient")
        if reward_func is not None:
            self.scorer = self._python_scorer(reward_func)
        else:
            self.scorer = {"kind": "declarative", "version": 1, "config": {}, **scorer}

    @staticmethod
    def _source(function, what):
        if not callable(function) or function.__name__ == "<lambda>" or function.__qualname__ != function.__name__:
            raise ValueError(f"a {what} function must be a named function at the top level of a .py file")
        path = inspect.getsourcefile(function)
        if path is None:
            raise ValueError(f"the {what} function's source file cannot be found (define it in a .py file)")
        return {"kind": "python", "path": path, "function": function.__name__}

    @classmethod
    def _python_scorer(cls, function):
        source = cls._source(function, "reward")
        name, version = getattr(function, "heteroes_scorer", (function.__name__.replace("_", "-").lower(), 1))
        return {
            "kind": "python",
            "name": name,
            "version": version,
            "path": source["path"],
            "function": function.__name__,
        }

    def config(self) -> dict:
        config = self.args.to_config(self.scorer)
        return config if self.coefficient_rule is None else {**config, "coefficientRule": self.coefficient_rule}

    def train(self, out_dir, device="cpu", workers=1, log=None, timeout_seconds=None):
        """Run every generation; returns their summaries. The run directory keeps recipe, plan, dataset, ledger and weights."""
        from heteroes.v3.local import run_local

        return run_local(
            self.config(), out_dir, device=device, workers=workers, log=log, timeout_seconds=timeout_seconds
        )
