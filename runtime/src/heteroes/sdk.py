"""
The Python entry point for researchers (ADR-008, owner decision 8): configure an ES experiment, give it a reward, train.

    from heteroes.sdk import ESConfig, ESTrainer, reward

    @reward("keyword-hit@1")                    # name@version: part of the plan, with the SHA-256 of this file
    def keyword_hit(completions, rows):         # one score per row; the reward of a candidate is their mean
        return [float(row["keyword"] in text) for text, row in zip(completions, rows)]

    args = ESConfig(model_path="models/my-model", model_id="my-org/my-model", train_dataset="data.jsonl",
                    prompt_field="question", population=16, generations=50, sigma=1e-3, alpha=1e-3, batch_size=32)
    ESTrainer(args, reward_func=keyword_hit).train("runs/first", device="cuda")

A reward function (and a coefficient rule or a sampler) is a named top-level function: in a .py file, whose source is
pinned, or in a notebook cell, whose own source is pinned (write its imports inside it). A changed function is a
different experiment. A declarative scorer (`scorer={"name": "answer-line-last-number"}`) needs no code.

`train()` runs on this machine with the lab's own coordinator, workers and protocol (`heteroes.v3.local`); nothing is
sent anywhere. `submit(lab, ...)` runs the same configuration on a shared lab (`heteroes.sdk_lab`).
"""

import builtins
import dis
import inspect
import textwrap
from dataclasses import dataclass, field
from pathlib import Path


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
    model_path: str | None = None  # or model=Model.from_hf(...) (heteroes.sdk_lab)
    model_id: str | None = None
    train_dataset: str | None = None  # or dataset=Dataset.from_rows(...)
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
    candidate_seed_namespace: str | None = None  # absent: run ID; reuse a namespace to compare resource layouts
    prompt_format: str | None = None  # absent: chat; raw sends the dataset prompt verbatim
    model: object = None  # heteroes.sdk_lab.Model: replaces model_path and model_id
    dataset: object = None  # heteroes.sdk_lab.Dataset: replaces train_dataset and prompt_field
    eval_chunks: list | None = None  # the chunks devices may use (ADR-010), e.g. from Lab.suggest; includes eval_chunk
    validation_interval: int | None = None  # a lab run: score the validation split every this many generations

    def __post_init__(self):
        if self.model is not None:
            self.model_path, self.model_id = self.model.path, self.model.id
        if self.dataset is not None:
            self.prompt_field = self.dataset.prompt_field
        if self.model_path is None or self.model_id is None or (self.train_dataset is None and self.dataset is None):
            raise ValueError("give a model (model= or model_path and model_id) and data (dataset= or train_dataset)")

    def _data(self):
        if self.dataset is None:
            return {"path": str(self.train_dataset)}
        files = self.dataset.files
        return {"path": files["all"]} if "all" in files else {"splits": dict(files)}

    def to_config(self, scorer: dict) -> dict:
        """The configuration `heteroes.v3.local.run_local` and `python -m heteroes.v3 run` read."""
        return {
            "model": {"path": str(self.model_path), "id": self.model_id},
            "data": {
                **self._data(),
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
            **({"promptFormat": self.prompt_format} if self.prompt_format is not None else {}),
            "evalDtype": self.eval_dtype,
            **({"evalChunk": self.eval_chunk} if self.eval_chunk is not None else {}),
            **({"evalChunks": list(self.eval_chunks)} if self.eval_chunks else {}),
            "decoder": self.decoder,
            "population": self.population,
            "generations": self.generations,
            "alpha": self.alpha,
            "coefficientRule": self.coefficient_rule,
            **(
                {"candidateSeedNamespace": self.candidate_seed_namespace}
                if self.candidate_seed_namespace is not None
                else {}
            ),
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


def self_contained(function, what):
    """The source of a function defined in a notebook cell, which must not read names from the notebook: those would not
    exist where the frozen code runs (the coordinator). ValueError names the first one."""
    source = textwrap.dedent(inspect.getsource(function))
    local = set(function.__code__.co_varnames)

    def globals_of(code):
        for instruction in dis.get_instructions(code):
            if instruction.opname in ("LOAD_GLOBAL", "LOAD_NAME") and instruction.argval not in local:
                yield instruction.argval
        for const in code.co_consts:
            if inspect.iscode(const):
                yield from globals_of(const)

    for name in globals_of(function.__code__):
        if not hasattr(builtins, name) and name != function.__name__:
            raise ValueError(
                f"the {what} function {function.__name__} reads {name!r} from the notebook: import or define it inside "
                "the function (the frozen code runs on the coordinator, without the notebook)"
            )
    return source


class ESTrainer:
    """Runs an `ESConfig` with a reward: a Python `reward_func` or a declarative `scorer` (exactly one of them).

    `coefficient_func(rewards) -> coefficients` replaces the coefficient rule; `sampler_func(generation, size,
    train_rows, seed) -> row numbers` chooses each generation's rows (a curriculum, for example). Both are pinned like
    a reward. `code_dir` keeps the frozen source of functions defined in a notebook cell."""

    def __init__(
        self,
        args: ESConfig,
        reward_func=None,
        scorer: dict | None = None,
        coefficient_func=None,
        sampler_func=None,
        code_dir="heteroes-code",
    ):
        if (reward_func is None) == (scorer is None):
            raise ValueError("give either reward_func (Python) or scorer (declarative)")
        self.args, self.code_dir = args, Path(code_dir)
        self.coefficient_rule = None if coefficient_func is None else self._source(coefficient_func, "coefficient")
        self.sampler = None if sampler_func is None else self._source(sampler_func, "sampler")
        if reward_func is not None:
            self.scorer = self._python_scorer(reward_func)
        else:
            self.scorer = {"kind": "declarative", "version": 1, "config": {}, **scorer}

    def _source(self, function, what):
        if not callable(function) or function.__name__ == "<lambda>" or function.__qualname__ != function.__name__:
            raise ValueError(f"a {what} function must be a named function at the top level of a .py file or a cell")
        path = inspect.getsourcefile(function)
        if path is None or not Path(path).is_file():
            # a notebook cell: its own source, frozen to a file named by its hash
            import hashlib

            source = self_contained(function, what)
            digest = hashlib.sha256(source.encode()).hexdigest()[:12]
            target = self.code_dir / f"{function.__name__}_{digest}.py"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(source, encoding="utf-8")
            path = str(target)
        return {"kind": "python", "path": path, "function": function.__name__}

    def _python_scorer(self, function):
        source = self._source(function, "reward")
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
        if self.sampler is not None:
            config["data"] = {**config["data"], "sampler": self.sampler}
        return config if self.coefficient_rule is None else {**config, "coefficientRule": self.coefficient_rule}

    def lab_spec(self, name=None) -> dict:
        """The configuration a shared lab receives (`heteroes.v3.lab_cli.offer_experiment`)."""
        spec = self.config()
        model = self.args.model
        if model is not None:
            spec["model"] = {**spec["model"], "revision": model.revision, "source": model.source}
        if self.args.validation_interval is not None:
            spec["validationInterval"] = self.args.validation_interval
        return {**spec, "name": name or f"{self.args.model_id} ES"}

    def submit(self, lab, coordinator, workers, name=None, directory=None, qualify=True, log=print):
        """Run on a shared lab: returns a `heteroes.sdk_lab.Run` at once (watch(), results(), cancel())."""
        return lab.submit(self, coordinator, workers, name=name, directory=directory, qualify=qualify, log=log)

    def train(self, out_dir, device="cpu", workers=1, log=None, timeout_seconds=None):
        """Run every generation; returns their summaries. The run directory keeps recipe, plan, dataset, ledger and weights."""
        from heteroes.v3.local import run_local

        return run_local(
            self.config(), out_dir, device=device, workers=workers, log=log, timeout_seconds=timeout_seconds
        )
