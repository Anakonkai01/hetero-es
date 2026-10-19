"""scripts/lab_replay.py reveals a recorded run bit by bit, so the live screens can be exercised without a GPU."""

import importlib.util
import json
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "lab_replay.py"
spec = importlib.util.spec_from_file_location("lab_replay", SCRIPT)
lab_replay = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lab_replay)
RUN = json.loads((Path(__file__).parent / "fixtures" / "run-d09d6ea8.json").read_text())
START = RUN["snapshot"]["state"]["startedAt"]
END = RUN["snapshot"]["state"]["completedAt"]


def at(seconds):
    return lab_replay.reveal(RUN, START + seconds)


def test_before_anything_ran_the_run_is_empty_but_running():
    body, snapshot = at(0.0)
    assert body["status"] == "RUNNING" and snapshot["state"]["status"] == "RUNNING"
    assert snapshot["attempts"] == [] and snapshot["candidates"] == [] and snapshot["generations"] == []


def test_halfway_some_attempts_are_finished_some_running_and_nothing_is_from_the_future():
    body, snapshot = at((END - START) * 0.35)
    statuses = {a["status"] for a in snapshot["attempts"]}
    assert statuses <= {"RUNNING", "SUCCEEDED", "FAILED"} and snapshot["attempts"]
    assert all(a["completedAt"] is None for a in snapshot["attempts"] if a["status"] == "RUNNING")
    assert all(e["t"] <= START + (END - START) * 0.35 for e in snapshot["events"])
    open_generation = [g for g in snapshot["generations"] if g["status"] == "RUNNING"]
    assert open_generation and "rewardMean" not in open_generation[-1]
    by_status = {c["status"] for c in snapshot["candidates"]}
    assert by_status <= {"PENDING", "RUNNING", "COMMITTED"}
    assert all("reward" not in c or c["reward"] is None for c in snapshot["candidates"] if c["status"] != "COMMITTED")


def test_the_revealed_part_only_grows_with_time():
    sizes = [
        (
            len(at(s)[1]["attempts"]),
            len(at(s)[1]["events"]),
            sum(c["status"] == "COMMITTED" for c in at(s)[1]["candidates"]),
        )
        for s in range(0, int(END - START) + 2, 7)
    ]
    assert sizes == sorted(sizes)


def test_at_the_end_the_whole_recorded_run_comes_back_completed():
    body, snapshot = at(END - START + 5)
    assert body["status"] == "COMPLETED" and snapshot["state"]["status"] == "COMPLETED"
    assert len(snapshot["attempts"]) == len(RUN["snapshot"]["attempts"]) and len(snapshot["events"]) == len(
        RUN["snapshot"]["events"]
    )
    assert [c["status"] for c in snapshot["candidates"]] == [c["status"] for c in RUN["snapshot"]["candidates"]]


def test_the_recording_itself_is_never_modified():
    before = json.dumps(RUN, sort_keys=True)
    at(10), at(60), at(500)
    assert json.dumps(RUN, sort_keys=True) == before


def test_shifting_moves_every_time_by_the_same_amount_and_keeps_the_durations():
    shifted = lab_replay.shift(RUN, 1000.0)
    first, second = RUN["snapshot"]["attempts"][0], shifted["snapshot"]["attempts"][0]
    gap = lab_replay._epoch(second["startedAt"]) - lab_replay._epoch(first["startedAt"])
    assert abs(gap - 1000.0) < 1e-3
    assert (
        abs(
            (lab_replay._epoch(second["completedAt"]) - lab_replay._epoch(second["startedAt"]))
            - (lab_replay._epoch(first["completedAt"]) - lab_replay._epoch(first["startedAt"]))
        )
        < 1e-3
    )
    assert shifted["snapshot"]["state"]["startedAt"] == RUN["snapshot"]["state"]["startedAt"] + 1000.0
    assert shifted["snapshot"]["events"][3]["t"] == RUN["snapshot"]["events"][3]["t"] + 1000.0
    assert shifted["snapshot"]["candidates"][0]["seed"] == RUN["snapshot"]["candidates"][0]["seed"], (
        "non-time fields are untouched"
    )
    assert shifted["body"]["name"] == RUN["body"]["name"]


def test_a_shifted_recording_reveals_the_same_way_relative_to_its_own_start():
    shifted = lab_replay.shift(RUN, 5000.0)
    start = shifted["snapshot"]["state"]["startedAt"]
    original = lab_replay.reveal(RUN, START + 30)[1]
    again = lab_replay.reveal(shifted, start + 30)[1]
    assert len(original["attempts"]) == len(again["attempts"]) and len(original["events"]) == len(again["events"])
    assert [c["status"] for c in original["candidates"]] == [c["status"] for c in again["candidates"]]
    assert json.dumps(RUN, sort_keys=True) == json.dumps(
        json.loads((Path(__file__).parent / "fixtures" / "run-d09d6ea8.json").read_text()), sort_keys=True
    )
