"""
The coordinator's side of the worker protocol: `WorkerAPI.handle(operation, request) -> reply`.

Requests and replies are plain JSON values, so a network layer only has to carry them. A reply is {"ok": true, ...} or
{"ok": false, "error": {"code": ..., "message": ...}}; the codes are part of the protocol and are spelled out here.
Every test sends a request through JSON text first, so nothing that is not JSON can sneak across.
"""
import json
import re
import sqlite3

import pytest

from heteroes.ledger import (
    AlreadyLeasedError,
    ConflictingResultError,
    ConflictingUpdateError,
    FailureKind,
    GenerationFailedError,
    GenerationNotCompleteError,
    Ledger,
    LedgerError,
    RecordMismatchError,
    ResultMismatchError,
    RetriesExhaustedError,
    StaleAttemptError,
    WorkerQuarantinedError,
)
from heteroes.worker_api import ERROR_CODES, WorkerAPI
from ledger_helpers import FakeClock, batch, descriptor_of

LEASE_SECONDS = 30.0


@pytest.fixture
def clock():
    return FakeClock()


@pytest.fixture
def ledger(clock):
    with Ledger(":memory:", clock=clock) as ledger:
        ledger.open_generation(batch(3))
        yield ledger


@pytest.fixture
def api(ledger):
    return WorkerAPI(ledger, "exp", 0, lease_seconds=LEASE_SECONDS)


def call(api, operation, request):
    reply = api.handle(operation, json.loads(json.dumps(request)))
    assert json.loads(json.dumps(reply)) == reply, "the reply must be pure JSON"
    return reply


def code_of(reply):
    assert reply["ok"] is False, reply
    assert set(reply) == {"ok", "error"} and set(reply["error"]) == {"code", "message"}
    return reply["error"]["code"]


def take(api, worker="worker-a"):
    reply = call(api, "lease", {"worker_id": worker})
    assert reply["ok"] is True and reply["work"] is not None, reply
    return reply["work"]


def result_request(work, reward=0.5, **changes):
    request = {"descriptor": work["descriptor"], "attempt_number": work["attempt_number"], "token": work["token"],
               "reward": reward}
    request.update(changes)
    return request


def failure_request(work, kind="OTHER", **changes):
    request = {"descriptor": work["descriptor"], "attempt_number": work["attempt_number"], "token": work["token"],
               "kind": kind}
    request.update(changes)
    return request


def deliver(api, work, reward=0.5):
    reply = call(api, "submit_result", result_request(work, reward))
    assert reply["ok"] is True, reply
    return reply


def fail(api, work, kind="OTHER"):
    reply = call(api, "report_failure", failure_request(work, kind))
    assert reply["ok"] is True, reply


def index_of(work):
    return work["descriptor"]["index"]


# ---------------------------------------------------------------------------
# lease: the coordinator picks the candidate
# ---------------------------------------------------------------------------

def test_a_lease_gives_the_first_candidate_with_everything_the_worker_needs(api, ledger, clock):
    reply = call(api, "lease", {"worker_id": "worker-a"})

    assert reply["ok"] is True and reply["generation_state"] == "OPEN"
    work = reply["work"]
    assert set(work) == {"descriptor", "attempt_number", "token", "deadline"}
    assert work["descriptor"] == descriptor_of(0).to_dict()
    assert work["attempt_number"] == 1
    assert re.fullmatch(r"[0-9a-f]{32}", work["token"])
    assert work["deadline"] == clock.now + LEASE_SECONDS
    held = ledger.get_candidate("exp/g0/c0")
    assert held.state.name == "LEASED" and held.attempts == 1


def test_the_length_of_the_lease_is_the_coordinators_choice(ledger, clock):
    api = WorkerAPI(ledger, "exp", 0, lease_seconds=12.5)

    assert take(api)["deadline"] == clock.now + 12.5
    reply = call(api, "lease", {"worker_id": "worker-b", "duration": 1e9})
    assert code_of(reply) == "bad_request"          # a worker cannot ask for a longer lease


def test_each_lease_goes_to_the_next_candidate_with_its_own_token(api):
    works = [take(api, f"worker-{i}") for i in range(3)]

    assert [index_of(w) for w in works] == [0, 1, 2]
    assert len({w["token"] for w in works}) == 3


def test_with_every_candidate_held_there_is_no_work_but_the_generation_is_open(api, ledger):
    for _ in range(3):
        take(api)

    reply = call(api, "lease", {"worker_id": "worker-b"})

    assert reply == {"ok": True, "generation_state": "OPEN", "work": None}
    assert ledger.get_generation_status("exp", 0).state.name == "OPEN"


def test_a_candidate_whose_lease_ran_out_is_given_again_before_a_fresh_one(api, clock):
    first = take(api)
    clock.advance(LEASE_SECONDS)                     # the deadline itself is already over

    again = take(api, "worker-b")

    assert index_of(again) == 0 and again["attempt_number"] == 2     # not candidate 1, which was never leased
    assert again["token"] != first["token"]


def test_a_candidate_that_failed_is_given_again_at_once(api):
    fail(api, take(api), "OUT_OF_MEMORY")

    again = take(api, "worker-b")

    assert index_of(again) == 0 and again["attempt_number"] == 2


def test_a_complete_generation_has_no_work(api):
    for _ in range(3):
        deliver(api, take(api))

    assert call(api, "lease", {"worker_id": "worker-a"}) == {"ok": True, "generation_state": "COMPLETE", "work": None}


def test_a_failed_generation_has_no_work_even_though_candidates_are_waiting(api, ledger):
    held = take(api)                                  # candidate 0 stays held, so the next free one is candidate 1
    for i in range(3):                                # candidate 1 uses all its attempts (on three workers: Greedy gives a failed candidate to another)
        work = take(api, f"worker-b{i}")
        assert index_of(work) == 1
        fail(api, work)
    assert ledger.get_candidate("exp/g0/c2").attempts == 0      # premise: there is a candidate nobody has tried

    reply = call(api, "lease", {"worker_id": "worker-c"})

    assert reply == {"ok": True, "generation_state": "FAILED", "work": None}
    assert held["attempt_number"] == 1
    assert ledger.get_candidate("exp/g0/c2").attempts == 0      # nothing was given out


def test_the_api_serves_only_its_own_generation(ledger):
    ledger.open_generation(batch(2, generation=1))
    api = WorkerAPI(ledger, "exp", 1, lease_seconds=LEASE_SECONDS)

    work = take(api)

    assert work["descriptor"]["generation"] == 1 and work["descriptor"]["index"] == 0
    assert ledger.get_candidate("exp/g0/c0").attempts == 0


def test_a_quarantined_worker_is_told_so_even_when_there_is_no_work(api):
    fail(api, take(api), "RESTORE_MISMATCH")

    assert code_of(call(api, "lease", {"worker_id": "worker-a"})) == "worker_quarantined"

    first = take(api, "worker-b")
    assert first["attempt_number"] == 2                          # premise: another worker is not affected
    deliver(api, first)
    for _ in range(2):
        deliver(api, take(api, "worker-b"))
    assert call(api, "lease", {"worker_id": "worker-b"})["generation_state"] == "COMPLETE"
    assert code_of(call(api, "lease", {"worker_id": "worker-a"})) == "worker_quarantined"


# ---------------------------------------------------------------------------
# submit_result
# ---------------------------------------------------------------------------

def test_a_result_is_committed(api, ledger):
    work = take(api)

    reply = call(api, "submit_result", result_request(work, 0.75))

    assert reply == {"ok": True, "outcome": "COMMITTED"}
    record = ledger.get_candidate("exp/g0/c0")
    assert record.state.name == "COMMITTED" and record.result.reward == 0.75 and record.result.attempt_number == 1


def test_the_same_result_again_is_acknowledged_and_changes_nothing(api, ledger):
    work = take(api)
    deliver(api, work, 0.75)
    before = ledger.list_candidates("exp", 0)

    reply = call(api, "submit_result", result_request(work, 0.75))

    assert reply == {"ok": True, "outcome": "ALREADY_COMMITTED"}
    assert ledger.list_candidates("exp", 0) == before


def test_another_reward_for_a_committed_candidate_is_refused_and_the_first_stays(api, ledger):
    work = take(api)
    deliver(api, work, 0.75)

    reply = call(api, "submit_result", result_request(work, 0.25))

    assert code_of(reply) == "conflicting_result"
    assert ledger.get_candidate("exp/g0/c0").result.reward == 0.75


def test_a_wrong_token_is_a_stale_attempt(api, ledger):
    work = take(api)

    reply = call(api, "submit_result", result_request(work, token="0" * 32))

    assert code_of(reply) == "stale_attempt"
    assert ledger.get_candidate("exp/g0/c0").result is None


def test_an_attempt_that_was_replaced_is_stale_and_the_new_one_wins(api, ledger, clock):
    slow = take(api, "worker-slow")
    clock.advance(LEASE_SECONDS)
    quick = take(api, "worker-quick")
    deliver(api, quick, 0.5)

    reply = call(api, "submit_result", result_request(slow, 0.9))

    assert code_of(reply) == "stale_attempt" and "exp/g0/c0" in reply["error"]["message"]
    record = ledger.get_candidate("exp/g0/c0")
    assert record.result.reward == 0.5 and record.result.attempt_number == 2


def test_the_latest_attempt_may_deliver_after_its_deadline_if_nobody_took_over(api, ledger, clock):
    work = take(api)
    clock.advance(10 * LEASE_SECONDS)

    assert deliver(api, work, 0.5) == {"ok": True, "outcome": "COMMITTED"}
    assert ledger.get_candidate("exp/g0/c0").state.name == "COMMITTED"


def test_a_result_for_another_job_is_refused(api, ledger):
    work = take(api)
    other = dict(work["descriptor"], seed=work["descriptor"]["seed"] + 1)

    reply = call(api, "submit_result", result_request(work, descriptor=other))

    assert code_of(reply) == "result_mismatch"
    assert ledger.get_candidate("exp/g0/c0").result is None


def test_a_result_for_a_candidate_the_ledger_does_not_have_is_refused(api):
    work = take(api)
    unknown = dict(work["descriptor"], index=7, seed=424242)

    assert code_of(call(api, "submit_result", result_request(work, descriptor=unknown))) == "rejected"


def test_a_quarantined_worker_cannot_deliver_and_its_lease_just_runs_out(api, ledger, clock):
    held = take(api)                                  # candidate 0
    doomed = take(api)                                # candidate 1, the same worker
    fail(api, doomed, "RESTORE_MISMATCH")

    reply = call(api, "submit_result", result_request(held))

    assert code_of(reply) == "worker_quarantined"
    assert ledger.get_candidate("exp/g0/c0").state.name == "LEASED"
    clock.advance(LEASE_SECONDS)
    assert index_of(take(api, "worker-b")) == 0       # another worker can have it


# ---------------------------------------------------------------------------
# report_failure
# ---------------------------------------------------------------------------

def test_a_failure_frees_the_candidate_and_is_never_a_result(api, ledger):
    work = take(api)

    reply = call(api, "report_failure", failure_request(work, "OUT_OF_MEMORY"))

    assert reply == {"ok": True}
    record = ledger.get_candidate("exp/g0/c0")
    assert record.state.name == "PENDING" and record.attempts == 1 and record.result is None


def test_the_same_failure_again_is_acknowledged_another_kind_is_not(api):
    work = take(api)
    fail(api, work, "OUT_OF_MEMORY")

    assert call(api, "report_failure", failure_request(work, "OUT_OF_MEMORY")) == {"ok": True}
    assert code_of(call(api, "report_failure", failure_request(work, "OTHER"))) == "conflicting_result"


def test_a_failure_of_an_old_attempt_is_stale(api, clock):
    old = take(api)
    clock.advance(LEASE_SECONDS)
    take(api, "worker-b")

    assert code_of(call(api, "report_failure", failure_request(old))) == "stale_attempt"


def test_a_failed_restore_puts_the_worker_in_quarantine(api, ledger):
    fail(api, take(api, "worker-a"), "RESTORE_MISMATCH")

    assert [q.worker_id for q in ledger.list_quarantined()] == ["worker-a"]


# ---------------------------------------------------------------------------
# the error codes are part of the protocol
# ---------------------------------------------------------------------------

def _all_subclasses(cls):
    for sub in cls.__subclasses__():
        yield sub
        yield from _all_subclasses(sub)


def test_the_codes_of_the_errors_a_worker_can_meet_are_fixed():
    assert {cls.__name__: code for cls, code in ERROR_CODES.items()} == {
        "LedgerError": "rejected",
        "LedgerBusyError": "busy",
        "AlreadyLeasedError": "already_leased",
        "RetriesExhaustedError": "retries_exhausted",
        "StaleAttemptError": "stale_attempt",
        "ResultMismatchError": "result_mismatch",
        "ConflictingResultError": "conflicting_result",
        "GenerationFailedError": "generation_failed",
        "GenerationNotCompleteError": "generation_not_complete",
        "WorkerQuarantinedError": "worker_quarantined",
        "RecordMismatchError": "record_mismatch",
        "ConflictingUpdateError": "conflicting_update",
    }


def test_no_error_of_the_ledger_is_left_without_a_code_of_its_own():
    covered = set(ERROR_CODES)
    assert LedgerError in covered
    assert set(_all_subclasses(LedgerError)) <= covered
    assert len(set(ERROR_CODES.values())) == len(ERROR_CODES)
    assert {AlreadyLeasedError, RetriesExhaustedError, StaleAttemptError, ResultMismatchError, ConflictingResultError,
            GenerationFailedError, GenerationNotCompleteError, WorkerQuarantinedError, RecordMismatchError,
            ConflictingUpdateError} <= covered


def test_an_error_that_has_no_code_yet_gets_the_code_of_its_nearest_parent(api, ledger, monkeypatch):
    class NewKindOfRefusal(StaleAttemptError):
        pass

    def refuse(*args, **kwargs):
        raise NewKindOfRefusal("a refusal that did not exist when the table was written")

    monkeypatch.setattr(ledger, "lease", refuse)

    assert code_of(call(api, "lease", {"worker_id": "worker-a"})) == "stale_attempt"


# ---------------------------------------------------------------------------
# bad requests: refused with a code, and nothing in the ledger moves
# ---------------------------------------------------------------------------

def _without(request, key):
    return {k: v for k, v in request.items() if k != key}


def _with(request, **changes):
    return dict(request, **changes)


def _bad_lease_requests():
    good = {"worker_id": "worker-a"}
    return {
        "not an object (list)": ["worker-a"],
        "not an object (null)": None,
        "not an object (text)": "worker-a",
        "worker_id missing": {},
        "worker_id empty": _with(good, worker_id=""),
        "worker_id a number": _with(good, worker_id=5),
        "worker_id null": _with(good, worker_id=None),
        "worker_id a list": _with(good, worker_id=["a"]),
        "an extra field": _with(good, duration=10),
    }


def _bad_result_requests(work):
    good = result_request(work)
    descriptor = work["descriptor"]
    bad = {
        "not an object": [good],
        "extra field": _with(good, worker_id="worker-a"),
        "descriptor missing": _without(good, "descriptor"),
        "descriptor null": _with(good, descriptor=None),
        "descriptor text": _with(good, descriptor="exp/g0/c0"),
        "descriptor empty": _with(good, descriptor={}),
        "descriptor key missing": _with(good, descriptor=_without(descriptor, "seed")),
        "descriptor extra key": _with(good, descriptor=_with(descriptor, worker="a")),
        "descriptor seed text": _with(good, descriptor=_with(descriptor, seed="7")),
        "descriptor seed negative": _with(good, descriptor=_with(descriptor, seed=-1)),
        "attempt_number missing": _without(good, "attempt_number"),
        "attempt_number text": _with(good, attempt_number="1"),
        "attempt_number bool": _with(good, attempt_number=True),
        "attempt_number float": _with(good, attempt_number=1.0),
        "attempt_number null": _with(good, attempt_number=None),
        "token missing": _without(good, "token"),
        "token a number": _with(good, token=5),
        "token null": _with(good, token=None),
        "reward missing": _without(good, "reward"),
        "reward text": _with(good, reward="0.5"),
        "reward bool": _with(good, reward=True),
        "reward null": _with(good, reward=None),
        "reward nan": _with(good, reward=float("nan")),
        "reward inf": _with(good, reward=float("inf")),
        "reward -inf": _with(good, reward=float("-inf")),
    }
    return bad


def _bad_failure_requests(work):
    good = failure_request(work)
    return {
        "not an object": "OTHER",
        "extra field": _with(good, reward=0.0),
        "descriptor null": _with(good, descriptor=None),
        "descriptor key missing": _with(good, descriptor=_without(work["descriptor"], "index")),
        "attempt_number text": _with(good, attempt_number="1"),
        "token null": _with(good, token=None),
        "kind missing": _without(good, "kind"),
        "kind unknown": _with(good, kind="BOGUS"),
        "kind lowercase": _with(good, kind="out_of_memory"),
        "kind a number": _with(good, kind=1),
        "kind null": _with(good, kind=None),
        "kind a list": _with(good, kind=["OTHER"]),
    }


def _case_names():
    probe_work = {"descriptor": descriptor_of(0).to_dict(), "attempt_number": 1, "token": "0" * 32}
    names = [("lease", name) for name in _bad_lease_requests()]
    names += [("submit_result", name) for name in _bad_result_requests(probe_work)]
    names += [("report_failure", name) for name in _bad_failure_requests(probe_work)]
    return names


@pytest.mark.parametrize("operation, name", _case_names(), ids=lambda value: str(value))
def test_a_malformed_request_is_a_bad_request_and_nothing_moves(api, ledger, operation, name):
    work = take(api)
    bad = {"lease": lambda: _bad_lease_requests(),
           "submit_result": lambda: _bad_result_requests(work),
           "report_failure": lambda: _bad_failure_requests(work)}[operation]()[name]
    candidates, quarantined = ledger.list_candidates("exp", 0), ledger.list_quarantined()

    reply = call(api, operation, bad)

    assert code_of(reply) == "bad_request"
    assert ledger.list_candidates("exp", 0) == candidates and ledger.list_quarantined() == quarantined

    good = {"lease": {"worker_id": "worker-b"}, "submit_result": result_request(work),
            "report_failure": failure_request(work)}[operation]
    assert call(api, operation, good)["ok"] is True       # premise: the request was refused for its shape, and the attempt is still usable


@pytest.mark.parametrize("operation", ["nope", "", "Lease", "handle", "__init__", "lease ", 5, None, ["lease"], {"lease": 1}])
def test_an_unknown_operation_is_refused_with_a_code(api, operation):
    assert code_of(api.handle(operation, {"worker_id": "worker-a"})) == "unknown_operation"


def test_a_bug_in_the_coordinator_is_not_dressed_up_as_a_bad_request(ledger):
    api = WorkerAPI(ledger, "exp", 0, lease_seconds=LEASE_SECONDS)
    ledger.close()

    with pytest.raises(sqlite3.ProgrammingError):
        api.handle("lease", {"worker_id": "worker-a"})
