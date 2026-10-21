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
    finished = dict(timeline(), experiment={**timeline()["experiment"], "status": "COMPLETED", "completedMs": T0 + 90_000})
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
