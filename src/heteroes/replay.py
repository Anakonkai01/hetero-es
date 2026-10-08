"""
Replay as a way for a worker to catch up (C4, MASTER section 11): instead of downloading the new weights (about 1 GB), fetch the update records
that turned its weights into the job's (a few hundred bytes each) and apply them with the same noise engine and the same arithmetic as the coordinator.

    ReplayPolicy    when replaying is worth it: `never`, `always`, or `auto` (the estimated replay seconds against the estimated synchronization seconds,
                    both from the worker's own profile; replay wins on a slow link or a fast GPU, loses otherwise: STATUS, `2026-10-08-c4-replay`)
    fetch_chain     the records from the worker's weights to the job's parent weights, each one checked against its own hash and its parent
    replay_chain    apply them to the model and take the result as the new parent, comparing the hash of the weights with the coordinator's

Replay never changes what the experiment is: a worker that replays has the weights the coordinator has, or it does not accept them (`ReplayFailed`) and the caller falls
back to a full synchronization, which overwrites every weight. The hash of the whole weights costs a pass over 1 GB (3.6 s on the 1660S), so the check can be made every
`verify_every` catch-ups instead of every time: between two checks the worker TRUSTS the coordinator's child hash, and a drift would go unseen until the next check.
The default is every time.
"""
import re
from dataclasses import dataclass

from heteroes.generation_record import GenerationRecord

MODES = ("never", "always", "auto")
DEFAULT_VERIFY_SECONDS = 3.6                  # one SHA-256 pass over the 1 GB of weights on the 1660S's CPU (STATUS, G6)
MAX_CHAIN = 8                                 # a worker further behind than this synchronizes
_HEX64 = re.compile(r"[0-9a-f]{64}")


class ReplayFailed(Exception):
    """The worker could not (or should not) replay: the reason is in the message, and the caller synchronizes instead."""


@dataclass(frozen=True)
class ReplayPolicy:
    mode: str = "never"
    update_seconds_per_candidate: float | None = None
    update_fixed_seconds: float = 0.0
    sync_seconds: float | None = None
    verify_seconds: float = DEFAULT_VERIFY_SECONDS
    verify_every: int = 1
    max_chain: int = MAX_CHAIN              # a worker further behind than this many updates synchronizes; raise it for a late joiner that replays from the base weights

    def __post_init__(self):
        if self.mode not in MODES:
            raise ValueError(f"mode must be one of {MODES}, got {self.mode!r}")
        if isinstance(self.verify_every, bool) or not isinstance(self.verify_every, int) or self.verify_every < 1:
            raise ValueError(f"verify_every must be an integer of at least 1, got {self.verify_every!r}")
        if isinstance(self.max_chain, bool) or not isinstance(self.max_chain, int) or self.max_chain < 1:
            raise ValueError(f"max_chain must be an integer of at least 1, got {self.max_chain!r}")

    @classmethod
    def from_profile(cls, profile: dict, mode: str = "auto", verify_every: int = 1, max_chain: int = MAX_CHAIN) -> "ReplayPolicy":
        """The numbers of the worker's own profile (`scripts/profile_worker.py --measure-update --sync-url ...`)."""
        update, sync = profile.get("update"), profile.get("sync")
        return cls(mode=mode,
                   update_seconds_per_candidate=None if update is None else update["seconds_per_candidate_median"],
                   update_fixed_seconds=0.0 if update is None else max(0.0, update.get("fixed_seconds", 0.0)),
                   sync_seconds=None if sync is None else sync["total_seconds"],
                   verify_seconds=DEFAULT_VERIFY_SECONDS if update is None else update.get("hash_seconds", DEFAULT_VERIFY_SECONDS),
                   verify_every=verify_every, max_chain=max_chain)

    def estimate_replay_seconds(self, steps: int, candidates: int, verified: bool = True) -> float | None:
        if self.update_seconds_per_candidate is None:
            return None
        return steps * (self.update_fixed_seconds + self.update_seconds_per_candidate * candidates) + (self.verify_seconds if verified else 0.0)

    def decide(self, steps: int, candidates: int) -> tuple[bool, str]:
        """(replay?, why) for a catch-up of `steps` updates of `candidates` candidates each."""
        if self.mode == "never":
            return False, "mode never"
        if self.mode == "always":
            return True, "mode always"
        replay = self.estimate_replay_seconds(steps, candidates)
        if replay is None or self.sync_seconds is None:
            return False, "auto without the update cost or the synchronization time in the profile"
        better = replay < self.sync_seconds
        return better, f"estimated replay {replay:.1f} s against synchronization {self.sync_seconds:.1f} s"


def fetch_chain(client, from_sha256: str, to_sha256: str, recipe_hash: str, max_steps: int = MAX_CHAIN) -> list[tuple[GenerationRecord, str]]:
    """
    [(record, child sha256), ...] from the weights `from_sha256` to `to_sha256`. Each record is checked against the hash the coordinator sent with it, against the
    weights it starts from and against the recipe. Raises ReplayFailed if the chain does not exist, is too long, loops, or has a record that is not what it says.
    """
    chain, current, seen = [], from_sha256, {from_sha256}
    while current != to_sha256:
        if len(chain) >= max_steps:
            raise ReplayFailed(f"the chain from {from_sha256[:12]} to {to_sha256[:12]} is longer than {max_steps} updates")
        update = client.get_update(current)
        if update is None:
            raise ReplayFailed(f"the coordinator has no update that starts from {current[:12]}")
        try:
            record = GenerationRecord.from_json(update["record_json"])
            child, record_hash = update["child_weights_sha256"], update["record_hash"]
        except (ValueError, TypeError, KeyError) as error:
            raise ReplayFailed(f"the update that starts from {current[:12]} is not a valid record: {error}") from error
        if not isinstance(child, str) or not _HEX64.fullmatch(child):
            raise ReplayFailed(f"the update that starts from {current[:12]} has no valid child hash")
        if record.hash != record_hash:
            raise ReplayFailed(f"the record that starts from {current[:12]} does not match its hash")
        if record.parent_weights_sha256 != current:
            raise ReplayFailed(f"the record served for {current[:12]} starts from {record.parent_weights_sha256[:12]}")
        if record.recipe_hash != recipe_hash:
            raise ReplayFailed(f"the record that starts from {current[:12]} is of another recipe")
        if child in seen:
            raise ReplayFailed(f"the chain loops back to {child[:12]}")
        seen.add(child)
        chain.append((record, child))
        current = child
    return chain


def replay_chain(executor, chain, apply_update, verify: bool) -> dict:
    """
    Apply the updates in order to the executor's model (`apply_update(model, schema, seeds, coefficients, alpha)`: the engine of the recipe) and make the result the
    executor's parent. With `verify` the hash of the weights must be the coordinator's child hash; without it the coordinator's hash is trusted. Raises ReplayFailed on a
    mismatch (the model then holds weights that are nobody's: the caller must synchronize). Returns the seconds it took.
    """
    import time
    started = time.perf_counter()
    for record, _child in chain:
        try:
            record.verify_coefficients(executor.recipe.reward_eta, atol=1e-6)
        except ValueError as error:
            raise ReplayFailed(f"generation {record.generation}: {error}") from error
        apply_update(executor.model, executor.schema, list(record.seeds), list(record.coefficients), record.alpha)
    applied = time.perf_counter()
    target = chain[-1][1]
    try:
        executor.reset_parent(target, trust=not verify)
    except ValueError as error:
        raise ReplayFailed(f"after {len(chain)} replayed updates {error}") from error
    done = time.perf_counter()
    return {"steps": len(chain), "apply_seconds": applied - started, "check_seconds": done - applied, "verified": verify}
