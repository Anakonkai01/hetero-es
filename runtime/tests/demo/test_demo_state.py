"""The GSM8K demo's frame builder, lab helpers and dashboard (pure, no network, no GPU)."""

import pytest

from heteroes.demo.lab import DemoLab, wait_until
from heteroes.demo.state import build_frame, load_frames, replay_frames, save_frames

T0 = 1_000_000  # ms


def timeline(now=T0 + 100_000):
    def job(c, w, g, start, end, reward, status="SUCCEEDED"):
        return {"candidateId": f"r.g{g}.c{c}", "workerId": w, "generation": g, "startMs": T0 + start * 1000,
                "endMs": None if end is None else T0 + end * 1000, "status": status, "reward": reward}  # fmt: skip

    return {
        "experiment": {"id": "r", "status": "RUNNING", "startedMs": T0, "maxGenerations": 3},
        "workers": [{"id": "fast", "alive": True}, {"id": "slow", "alive": False}],
        "generations": [
            {"index": 0, "openMs": T0, "doneMs": T0 + 30_000, "rewardMean": 0.5, "rewardBest": 0.75, "seconds": {}},
            {"index": 1, "openMs": T0 + 31_000, "doneMs": None, "rewardMean": None, "rewardBest": None},
        ],
        "jobs": [
            job(0, "fast", 0, 0, 10, 0.25),
            job(1, "slow", 0, 0, 25, 0.75),
            job(2, "fast", 0, 10, 20, None, "FAILED"),
            job(0, "fast", 1, 31, 40, 1.0),
            job(1, "fast", 1, 41, None, None, "RUNNING"),
        ],
        "marks": [],
        "nowMs": now,
    }


EVENTS = [
    {"eventType": "audit_completed", "details": {"t": (T0 + 20_000) / 1000, "worker_id": "slow"}},
    {"eventType": "audit_mismatch", "details": {"t": (T0 + 90_000) / 1000, "worker_id": "fast"}},
    {"eventType": "validation_completed", "details": {"t": (T0 + 29_000) / 1000, "generation": 0, "meanReward": 0.4}},
    {"event": "worker_left", "t": (T0 + 35_000) / 1000, "worker_id": "slow"},
    {"eventType": "audit_completed", "details": {"t": (T0 + 200_000) / 1000, "worker_id": "slow"}},  # in the future
]


def test_a_frame_counts_work_rewards_audits_and_membership_up_to_its_moment():
    frame = build_frame(timeline(), EVENTS, {"fast": "5070", "slow": "1660"})
    fast, slow = frame.devices
    assert (fast.name, fast.done, fast.done_now, fast.busy) == ("5070", 2, 1, "r.g1.c1")
    assert (slow.done, slow.alive, slow.audits) == (1, False, 1)
    assert fast.mismatches == 1 and frame.audits == {"matched": 1, "mismatched": 1}
    assert frame.generation == 1 and frame.now_s == 100.0
    assert frame.rewards == [{"generation": 0, "mean": 0.5, "best": 0.75, "seconds": {}, "atS": 30.0}]
    assert frame.scores == [1.0]  # the newest generation with a committed result
    assert frame.validation == [{"generation": 0, "reward": 0.4}]
    assert frame.membership == [{"atS": 35.0, "worker": "slow", "change": "left"}]
    assert [lane["ok"] for lane in frame.lanes] == [True, True, False, True, None]
    assert frame.lanes[-1]["end"] is None


def test_an_earlier_moment_hides_what_had_not_happened_yet():
    frame = build_frame(timeline(), EVENTS, at_ms=T0 + 15_000)
    fast, slow = frame.devices
    assert (fast.done, fast.busy, slow.busy) == (1, "r.g0.c2", "r.g0.c1")
    assert frame.rewards == [] and frame.scores == [0.25] and frame.audits["matched"] == 0
    assert frame.generation == 0 and len(frame.lanes) == 3
    finished = dict(
        timeline(), experiment={**timeline()["experiment"], "status": "COMPLETED", "completedMs": T0 + 90_000}
    )
    assert build_frame(finished, at_ms=T0 + 15_000).status == "RUNNING"
    assert build_frame(finished, at_ms=T0 + 95_000).status == "COMPLETED"


def test_replay_frames_round_trip_through_a_file(tmp_path):
    frames = replay_frames(timeline(), EVENTS, steps=5)
    assert [f.at_ms for f in frames] == [T0, T0 + 25_000, T0 + 50_000, T0 + 75_000, T0 + 100_000]
    save_frames(frames, tmp_path / "frames.jsonl")
    assert load_frames(tmp_path / "frames.jsonl") == frames


def test_the_lab_helpers_toggle_by_boot_and_follow_until_the_end():
    calls = []

    class Api:
        def request(self, method, path, body=None):
            calls.append((method, path, body))
            if path == "/api/v1/devices":
                return [{"workerId": "w", "deviceId": "d", "bootId": "b"}]
            if path.endswith("/timeline"):
                return dict(timeline(), experiment={**timeline()["experiment"], "status": "COMPLETED"})
            return []

    lab = DemoLab(api=Api())
    lab.set_contribution("w", False)
    assert calls[-1] == ("POST", "/api/v1/devices/d/contribution", {"enabled": False, "bootId": "b"})
    with pytest.raises(LookupError):
        lab.set_contribution("other", True)
    assert [f.status for f, _ in lab.follow("r", sleep=lambda s: None)] == ["COMPLETED"]
    with pytest.raises(TimeoutError):
        wait_until(lambda: None, 5, clock=iter([0, 6]).__next__, sleep=lambda s: None)
    assert wait_until(lambda: "yes", 5, clock=lambda: 0) == "yes"


def test_reads_are_retried_through_network_failures_but_not_through_lab_answers():
    failures = [OSError("reset"), RuntimeError("Lab HTTP 502: edge")]

    class Api:
        def request(self, method, path, body=None):
            if path == "/bad":
                raise RuntimeError("Lab HTTP 404: missing")
            if failures:
                raise failures.pop(0)
            return {"ok": method}

    lab = DemoLab(api=Api())
    assert lab.request("GET", "/x", sleep=lambda s: None) == {"ok": "GET"} and not failures
    with pytest.raises(RuntimeError, match="404"):
        lab.request("GET", "/bad", sleep=lambda s: None)
    failures.append(OSError("reset"))
    with pytest.raises(OSError):  # a write is never repeated behind the caller's back
        lab.request("POST", "/x", {}, sleep=lambda s: None)


def test_the_dashboard_draws_a_frame(tmp_path):
    from heteroes.demo.dashboard import Dashboard

    Dashboard("5070ti-nhan").save(build_frame(timeline(), EVENTS), tmp_path / "frame.png")
    assert (tmp_path / "frame.png").stat().st_size > 20_000


def test_the_member_story_merges_process_and_ledger_records_in_time_order():
    from heteroes.demo.analysis import member_story

    lifecycle = [
        {"event": "worker_start_unknown", "t": 1000.0, "worker_id": "a"},  # routine at every start: not a story line
        {"event": "worker_restart_deferred", "t": 1300.0, "worker_id": "a", "launch": 1, "httpStatus": 409},
        {"event": "worker_restarted", "t": 1330.0, "worker_id": "a", "launch": 1},
    ]
    ledger = [
        {"at": 1000.0, "workerId": "a", "action": "JOIN", "generation": 0, "actor": "experiment"},
        {"at": 1200.0, "workerId": "a", "action": "LEAVE", "generation": 3, "actor": "system"},
    ]
    lost = [{"workerId": "a", "leasedAt": 1100.0, "deadline": 1160.0}]
    rows = member_story(lifecycle, ledger, {"a": "1660s"}, 1_000_000, lost, {"a": 1400.0})
    assert [(r["at (min)"], r["source"], r["what"]) for r in rows] == [
        (2.7, "ledger", "work lost: no answer by its deadline"),
        (3.3, "ledger", "LEAVE from generation 4"),
        (5.0, "coordinator", "not ON (yet): asked again in 30 s"),
        (5.5, "coordinator", "worker started again"),
        (6.7, "coordinator", "not answering (still, at this snapshot)"),
    ]
    assert {r["device"] for r in rows} == {"1660s"} and rows[3]["launch"] == 1


def test_a_ledger_join_draws_a_rejoin_and_a_process_and_ledger_pair_draws_once():
    # a re-added member has no worker_joined (RESULTS.md finding 9): its JOIN is the coordinator's membership_changed
    events = [
        {"eventType": "worker_left", "details": {"t": (T0 + 35_000) / 1000, "worker_id": "slow"}},
        {
            "eventType": "membership_changed",
            "details": {"t": (T0 + 36_000) / 1000, "workerId": "slow", "action": "LEAVE"},
        },
        {
            "eventType": "membership_changed",
            "details": {"t": (T0 + 60_000) / 1000, "workerId": "slow", "action": "JOIN"},
        },
    ]
    frame = build_frame(timeline(), events)
    assert [(m["atS"], m["worker"], m["change"]) for m in frame.membership] == [
        (35.0, "slow", "left"),
        (60.0, "slow", "joined"),
    ]

    from heteroes.demo.replay_page import recording

    assert recording(timeline(), events)["membership"] == [[35.0, 1, "left"], [60.0, 1, "joined"]]


def test_a_replayed_moment_does_not_show_the_end_state_of_the_workers():
    ended = timeline()
    ended["experiment"].update(status="COMPLETED", completedMs=T0 + 100_000)  # every worker stopped at the end
    ended["workers"] = [{"id": "fast", "alive": False}, {"id": "slow", "alive": False}]
    assert [d.alive for d in build_frame(ended, at_ms=T0 + 50_000).devices] == [None, None]
    assert [d.alive for d in build_frame(ended).devices] == [False, False]


def test_a_notebook_gets_the_dashboard_as_a_png_image():
    from heteroes.demo.dashboard import Dashboard, png

    image = png(Dashboard().draw(build_frame(timeline(), EVENTS)))
    assert image.format == "png" and image.data[:4] == b"\x89PNG" and len(image.data) > 20_000


def test_a_timeline_rebuilt_from_the_ledger_has_every_attempt(tmp_path):
    import json
    import sqlite3

    from heteroes.demo.ledger_view import ledger_events, ledger_timeline

    run = tmp_path / "r"
    run.mkdir()
    (run / "config.json").write_text(json.dumps({"workerIds": ["fast", "slow"]}))
    events = [
        {"event": "managed_start", "t": 100.0},
        {"event": "generation_open", "generation": 0, "t": 101.0},
        {"event": "audit_completed", "worker_id": "slow", "t": 130.0},
        {"event": "update_applied", "generation": 0, "t": 140.0},
        {"event": "generation_open", "generation": 1, "t": 141.0},
    ]
    (run / "events.jsonl").write_text("\n".join(json.dumps(e) for e in events) + "\n{partial")
    db = sqlite3.connect(run / "ledger.sqlite")
    db.execute("CREATE TABLE candidate (candidate_id, experiment_id, generation, candidate_index, seed, sign, state)")
    db.execute(
        "CREATE TABLE attempt (candidate_id, attempt_number, worker_id, lease_token, leased_at, deadline, ended_at, failure_kind)"
    )
    db.execute("CREATE TABLE result (candidate_id, attempt_number, reward, committed_at)")
    for cid, g in (("r/g0/c0", 0), ("r/g0/c1", 0), ("r/g1/c0", 1), ("r/g1/c1", 1)):
        db.execute("INSERT INTO candidate VALUES (?,?,?,0,1,1,'X')", (cid, "r", g))
    db.executemany(
        "INSERT INTO attempt VALUES (?,?,?,'t',?,?,?,NULL)",
        [
            ("r/g0/c0", 1, "fast", 102.0, 160.0, 110.0),  # committed
            ("r/g0/c1", 1, "slow", 102.0, 120.0, None),  # its machine died: lost at the deadline
            ("r/g0/c1", 2, "fast", 121.0, 180.0, 130.0),  # retried and committed
            ("r/g1/c0", 1, "fast", 142.0, 999.0, None),  # running now
        ],
    )
    db.executemany("INSERT INTO result VALUES (?,?,?,?)", [("r/g0/c0", 1, 0.5, 110.0), ("r/g0/c1", 2, 0.75, 130.0)])
    db.commit()
    db.close()
    t = ledger_timeline(run, now_s=150.0, name="n", max_generations=3, population=2)
    assert [(j["workerId"], j["status"], j["endMs"], j["reward"]) for j in t["jobs"]] == [
        ("fast", "SUCCEEDED", 110_000, 0.5),
        ("slow", "LOST", 120_000, None),
        ("fast", "SUCCEEDED", 130_000, 0.75),
        ("fast", "RUNNING", None, None),
    ]
    g0, g1 = t["generations"]
    assert (g0["status"], g0["openMs"], g0["doneMs"], g0["rewardMean"], g0["rewardBest"]) == (
        "COMPLETED",
        101_000,
        140_000,
        0.625,
        0.75,
    )
    assert (g1["status"], g1["rewardMean"]) == ("RUNNING", None)
    assert t["experiment"]["startedMs"] == 100_000 and t["nowMs"] == 150_000
    frame = build_frame(t, ledger_events(run), {"fast": "5070", "slow": "1660"})
    assert [(d.name, d.done, d.busy, d.audits) for d in frame.devices] == [
        ("5070", 2, "r/g1/c0", 0),
        ("1660", 0, None, 1),
    ]
