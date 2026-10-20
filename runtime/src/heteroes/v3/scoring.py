"""
Scoring on the coordinator (ADR-008 section 7): the reward of a candidate from the texts its worker submitted.

A scorer gives one finite score per row; the reward is their mean, summed in row order exactly like today's evaluations
(`sum(scores) / len(scores)`). A scorer that fails, or gives a score that is not a finite number, raises `ScorerError`: that
is a fault of the experiment's scoring, never a reward of 0 and never the worker's fault.

Declarative scorers are named and versioned; the three that exist today reuse today's extraction functions, so the rewards
of built-in workloads do not change when scoring moves from the worker to the coordinator. A Python scorer is any
`f(completions, rows) -> scores`, identified by name@version and the SHA-256 of its source files (`code_sha256`).
"""

import ast
import hashlib
import math
import operator
import re
from fractions import Fraction
from pathlib import Path


class ScorerError(Exception):
    pass


def _answer_line_last_number(text, row, config):
    from heteroes.study.evaluation import extract

    return 1.0 if extract(text) == row["answer"] else 0.0


def _last_integer(text, row, config):
    from heteroes.eval.workload import exact_match_reward, extract_integer

    return exact_match_reward(extract_integer(text), row["answer"])


def _answer_line_integer(text, row, config):
    from heteroes.eval.cot_workload import extract_answer

    return 1.0 if extract_answer(text) == row["answer"] else 0.0


def _regex(text, row, config):
    found = re.findall(config["pattern"], text)
    if not found:
        return 0.0
    last = found[-1]
    prediction = last[0] if isinstance(last, tuple) else last  # the first group when the pattern has groups
    return 1.0 if prediction.strip() == str(row[config["answerField"]]).strip() else 0.0


def _exact_string(text, row, config):
    def norm(value):
        value = value.strip() if config["strip"] else value
        return value.casefold() if config["casefold"] else value

    return 1.0 if norm(text) == norm(str(row[config["answerField"]])) else 0.0


_CHOICE = re.compile(r"\b([A-E])\b")


def _choice_letter(text, row, config):
    found = _CHOICE.findall(text)
    return 1.0 if found and found[-1] == str(row[config["answerField"]]).strip().upper() else 0.0


_ANSWER_TAG = re.compile(r"<answer>(.*?)</answer>", re.DOTALL)
_COUNTDOWN_OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv}


def _countdown_value(node, used):
    """The exact value of an expression of integers, + - * / and parentheses; None for anything else."""
    if isinstance(node, ast.Constant) and type(node.value) is int:
        used.append(node.value)
        return Fraction(node.value)
    if isinstance(node, ast.BinOp) and type(node.op) in _COUNTDOWN_OPS:
        left, right = _countdown_value(node.left, used), _countdown_value(node.right, used)
        if left is None or right is None or (isinstance(node.op, ast.Div) and right == 0):
            return None
        return _COUNTDOWN_OPS[type(node.op)](left, right)
    return None


def _countdown(text, row, config):
    # The reward of TinyZero / "Evolution Strategies at Scale": 1.0 for an equation in the last <answer> tag that uses
    # every given number exactly once and equals the target, 0.1 for any other answer, 0.0 without an answer. Unary
    # minus, powers and non-integers are not Countdown operations; the expression is parsed, never evaluated by Python.
    numbers = sorted(int(n) for n in re.split(r"[\s,\[\]]+", str(row[config["numbersField"]]).strip()) if n)
    target = Fraction(int(row[config["targetField"]]))
    found = _ANSWER_TAG.findall(text)
    if not found:
        return 0.0
    try:
        tree = ast.parse(found[-1].strip(), mode="eval")
    except (SyntaxError, ValueError):
        return 0.1
    used = []
    value = _countdown_value(tree.body, used)
    return 1.0 if value is not None and sorted(used) == numbers and value == target else 0.1


# name -> version -> (function, the exact set of config keys)
DECLARATIVE = {
    "answer-line-last-number": {1: (_answer_line_last_number, set())},  # Recipe v2 datasets (study/evaluation.py)
    "last-integer": {1: (_last_integer, set())},  # arith16 (eval/workload.py)
    "answer-line-integer": {1: (_answer_line_integer, set())},  # cot_* workloads (eval/cot_workload.py)
    "regex": {1: (_regex, {"pattern", "answerField"})},
    "exact-string": {1: (_exact_string, {"answerField", "strip", "casefold"})},
    "choice-letter": {1: (_choice_letter, {"answerField"})},
    "countdown": {1: (_countdown, {"numbersField", "targetField"})},
}
SPEC_KEYS = {"kind", "name", "version", "codeSha256", "config"}


def validate_spec(spec, *, allow_python=False):
    """Check a scorer spec of a plan; a shared lab passes allow_python=False (ADR-008 decision 4)."""
    if not isinstance(spec, dict) or set(spec) != SPEC_KEYS:
        raise ValueError(f"a scorer spec has exactly the keys {sorted(SPEC_KEYS)}")
    name, version, config = spec["name"], spec["version"], spec["config"]
    if not isinstance(name, str) or not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,63}", name):
        raise ValueError(f"invalid scorer name {name!r}")
    if type(version) is not int or version < 1:
        raise ValueError(f"invalid scorer version {version!r}")
    if not isinstance(config, dict):
        raise ValueError("a scorer config is an object")
    if spec["kind"] == "declarative":
        if spec["codeSha256"] is not None:
            raise ValueError("a declarative scorer has no code hash")
        if version not in DECLARATIVE.get(name, {}):
            raise ValueError(f"unknown declarative scorer {name}@{version}")
        keys = DECLARATIVE[name][version][1]
        if set(config) != keys:
            raise ValueError(f"{name}@{version} takes the config keys {sorted(keys)}")
        if name == "regex":
            if not isinstance(config["pattern"], str) or not 0 < len(config["pattern"]) <= 500:
                raise ValueError("a regex pattern is a nonempty string of at most 500 characters")
            try:
                re.compile(config["pattern"])
            except re.error as error:
                raise ValueError(f"invalid regex pattern: {error}") from None
        for field in sorted(k for k in keys if k.endswith("Field")):
            if not isinstance(config[field], str) or not config[field]:
                raise ValueError(f"{field} names a column of the dataset")
        for flag in {"strip", "casefold"} & keys:
            if type(config[flag]) is not bool:
                raise ValueError(f"{flag} is true or false")
    elif spec["kind"] == "python":
        if not allow_python:
            raise ValueError("this lab accepts only declarative scorers")
        if not isinstance(spec["codeSha256"], str) or not re.fullmatch("[0-9a-f]{64}", spec["codeSha256"]):
            raise ValueError("a Python scorer is pinned by the SHA-256 of its code")
    else:
        raise ValueError(f"unknown scorer kind {spec['kind']!r}")
    return spec


def source_sha256(name, content: bytes):
    """`code_sha256` of a single file called `name` with these bytes (a file uploaded to the web lab)."""
    digest = hashlib.sha256()
    digest.update(f"{name}\0{len(content)}\0".encode())
    digest.update(content)
    return digest.hexdigest()


def code_sha256(root):
    """The identity of a Python scorer's code: every .py file under `root`, by relative name and content, in name order."""
    root = Path(root)
    files = sorted(p for p in root.rglob("*.py") if "__pycache__" not in p.parts) if root.is_dir() else [root]
    if not files:
        raise ValueError(f"no Python source under {root}")
    digest = hashlib.sha256()
    for path in files:
        name = path.relative_to(root).as_posix() if root.is_dir() else path.name
        content = path.read_bytes()
        digest.update(f"{name}\0{len(content)}\0".encode())
        digest.update(content)
    return digest.hexdigest()


def _checked(scores, count):
    try:
        scores = list(scores)
    except TypeError:
        raise ScorerError("a scorer must return a sequence of scores") from None
    if len(scores) != count:
        raise ScorerError(f"the scorer gave {len(scores)} scores for {count} rows")
    for score in scores:
        if isinstance(score, bool) or not isinstance(score, (int, float)) or not math.isfinite(score):
            raise ScorerError(f"a score must be a finite number, got {score!r}")
    return [float(score) for score in scores]


def score(spec, completions, rows, python_scorer=None):
    """(reward, per-row scores) of one candidate. `python_scorer` is the loaded function of a Python spec."""
    if len(completions) != len(rows) or not rows:
        raise ScorerError(f"{len(completions)} texts for {len(rows)} rows")
    if not all(isinstance(text, str) for text in completions):
        raise ScorerError("every completion is a text")
    try:
        if spec["kind"] == "declarative":
            function = DECLARATIVE[spec["name"]][spec["version"]][0]
            raw = [function(text, row, spec["config"]) for text, row in zip(completions, rows)]
        elif python_scorer is None:
            raise ScorerError(f"the Python scorer {spec['name']}@{spec['version']} is not loaded")
        else:
            raw = python_scorer(list(completions), [dict(row) for row in rows])
    except ScorerError:
        raise
    except Exception as error:
        raise ScorerError(f"{spec['name']}@{spec['version']} failed: {type(error).__name__}: {error}") from error
    scores = _checked(raw, len(rows))
    return sum(scores) / len(scores), scores
