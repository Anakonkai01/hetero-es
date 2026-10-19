import json
import math
from dataclasses import dataclass

import numpy as np

from heteroes.canonical import canonical_json_bytes, canonical_json_hash
from heteroes.manifest import _HEX64, _NAME, MAX_SEED, _check_int, _check_keys, _check_text

RECORD_VERSION = 1
_FLOAT32_MAX = float(np.finfo(np.float32).max)


def _as_tuple(name: str, value) -> tuple:
    if not isinstance(value, (list, tuple)):
        raise TypeError(f"{name} must be a list or a tuple, got {type(value).__name__}")
    return tuple(value)


def _real(name: str, value) -> float:
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, float, np.integer, np.floating)):
        raise TypeError(f"{name} must be a number, got {type(value).__name__}")
    value = float(value)
    if not math.isfinite(value):
        raise ValueError(f"{name} must be finite, got {value}")
    return value


def _float32_value(name: str, value: float) -> float:
    with np.errstate(over="ignore"):
        exact = float(np.float32(value)) == value
    if not exact:
        raise ValueError(f"{name} must be exactly a float32 value (it would be rounded in silence), got {value}")
    return value


@dataclass(frozen=True)
class GenerationRecord:
    """
    What turns the parent weights of a generation into its child weights: the message a worker needs to replay one
    ES update without receiving the weights (a few hundred bytes instead of 1 GB), and what the coordinator writes down
    BEFORE it touches the weights, so that a crash cannot make the update happen twice.

    Inputs only. The weights that come out (`child_weights_sha256`) are an outcome, recorded apart by whoever applies the
    update: putting them here would change the hash of the record after the fact.

    The coefficients are computed ONCE, by the coordinator, and travel: nobody recomputes them from the rewards. (Where a
    reward equals the mean, the coefficient is 0.0 or a residue of about 1e-16 depending on the order in which the sum was
    made: measured in 0.3 to 0.4% of the sets of rewards k/96, harmless for the weights, but not the same bytes; see
    artifacts/experiments/2026-10-06-coefficient-residue.)
    The rewards stay in the record so that the coefficients can be audited (`verify_coefficients`).
    """
    experiment_id: str
    generation: int
    recipe_hash: str
    parent_weights_sha256: str
    seeds: tuple[int, ...]
    rewards: tuple[float, ...]
    coefficients: tuple[float, ...]
    alpha: float

    def __post_init__(self):
        _check_text("experiment_id", self.experiment_id, _NAME)
        _check_int("generation", self.generation, 0)
        _check_text("recipe_hash", self.recipe_hash, _HEX64)
        _check_text("parent_weights_sha256", self.parent_weights_sha256, _HEX64)

        seeds = _as_tuple("seeds", self.seeds)
        if not seeds:
            raise ValueError("a record needs at least one candidate")
        for seed in seeds:
            _check_int("seed", seed, 0, MAX_SEED)
        if len(set(seeds)) != len(seeds):
            raise ValueError("the seeds of a generation must all be different")
        rewards = tuple(_real("reward", value) for value in _as_tuple("rewards", self.rewards))
        coefficients = tuple(_float32_value("coefficient", _real("coefficient", value))
                             for value in _as_tuple("coefficients", self.coefficients))
        if not (len(seeds) == len(rewards) == len(coefficients)):
            raise ValueError(f"seeds, rewards and coefficients must have the same length "
                             f"({len(seeds)}, {len(rewards)}, {len(coefficients)})")
        alpha = _real("alpha", self.alpha)
        if abs(alpha) > _FLOAT32_MAX:
            raise ValueError(f"alpha does not fit in a float32, got {alpha}")

        object.__setattr__(self, "seeds", seeds)
        object.__setattr__(self, "rewards", rewards)
        object.__setattr__(self, "coefficients", coefficients)
        object.__setattr__(self, "alpha", alpha)

    @property
    def noop(self) -> bool:
        """No signal: every coefficient is zero, so the update changes nothing."""
        return not any(self.coefficients)

    def to_dict(self) -> dict:
        return {
            "record_version": RECORD_VERSION,
            "experiment_id": self.experiment_id,
            "generation": self.generation,
            "recipe_hash": self.recipe_hash,
            "parent_weights_sha256": self.parent_weights_sha256,
            "seeds": list(self.seeds),
            "rewards": list(self.rewards),
            "coefficients": list(self.coefficients),
            # the value the update really uses: derived here so that it can never disagree with alpha
            "alpha": self.alpha,
            "alpha_float32": float(np.float32(self.alpha)),
        }

    @property
    def hash(self) -> str:
        return canonical_json_hash(self.to_dict())

    def to_json(self) -> str:
        return canonical_json_bytes(self.to_dict()).decode("ascii")

    @classmethod
    def from_dict(cls, data: dict) -> "GenerationRecord":
        _check_keys("generation record", data, {
            "record_version", "experiment_id", "generation", "recipe_hash", "parent_weights_sha256", "seeds", "rewards",
            "coefficients", "alpha", "alpha_float32"})
        if data["record_version"] != RECORD_VERSION:
            raise ValueError(f"unknown record version {data['record_version']}")
        record = cls(
            experiment_id=data["experiment_id"], generation=data["generation"], recipe_hash=data["recipe_hash"],
            parent_weights_sha256=data["parent_weights_sha256"], seeds=data["seeds"], rewards=data["rewards"],
            coefficients=data["coefficients"], alpha=data["alpha"],
        )
        if record.to_dict() != data:
            raise ValueError("record does not round-trip (a derived value, such as alpha_float32, disagrees)")
        return record

    @classmethod
    def from_json(cls, text: str) -> "GenerationRecord":
        return cls.from_dict(json.loads(text))

    def verify_coefficients(self, eta: float, atol: float = 0.0) -> None:
        """
        Check that the coefficients are those of the rewards (reward standardization with `eta`, numerical contract 7).
        Exact by default: right for the coordinator that has just made them. `atol` is for an audit on another machine,
        where a coefficient that is 0.0 here may be a residue of 1e-16 there.
        """
        from heteroes.es.update import standardize_rewards     # needs torch; the record itself does not

        expected = standardize_rewards(self.rewards, eta).astype(np.float64)
        actual = np.asarray(self.coefficients, dtype=np.float32).astype(np.float64)
        same = np.array_equal(actual, expected) if atol == 0 else bool(np.all(np.abs(actual - expected) <= atol))
        if not same:
            raise ValueError("the coefficients are not those of the rewards")

    @classmethod
    def from_results(cls, experiment_id: str, generation: int, results, alpha: float, eta: float) -> "GenerationRecord":
        """The record of a complete generation (`results` is what `Ledger.get_generation_results` returns)."""
        from heteroes.es.update import standardize_rewards     # needs torch; the record itself does not

        coefficients = tuple(float(value) for value in standardize_rewards(results.rewards, eta))
        return cls(
            experiment_id=experiment_id, generation=generation, recipe_hash=results.recipe_hash,
            parent_weights_sha256=results.parent_weights_sha256, seeds=tuple(results.seeds),
            rewards=tuple(results.rewards), coefficients=coefficients, alpha=alpha,
        )
