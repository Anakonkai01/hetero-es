from monitor import FAILED, decide


def snap(applied, active=None, audits=(1, 0), quarantines=()):
    return {"applied": applied, "active": {FAILED: active or []}, "audits": list(audits), "quarantines": list(quarantines)}


def test_events_happen_once_in_order():
    flags = {}
    assert decide(flags, snap(9), "RUNNING", 0) == []
    assert decide(flags, snap(10), "RUNNING", 0) == ["join"]
    flags["joined"] = 1
    assert decide(flags, snap(19), "RUNNING", 0) == []  # no active main lease on the Windows worker: wait
    assert decide(flags, snap(19, [["c", 19, 1]]), "RUNNING", 100) == ["fault"]
    flags["stoppedAt"] = 100
    assert decide(flags, snap(20, [["c", 19, 1]]), "RUNNING", 399) == []
    assert decide(flags, snap(21), "RUNNING", 400) == ["relaunch"]
    flags["relaunched"] = 400
    assert decide(flags, snap(22), "RUNNING", 410) == ["contribution"]
    flags["contributionOn"] = 420
    assert decide(flags, snap(30), "RUNNING", 900) == ["leave"]
    flags["left"] = 900
    assert decide(flags, snap(40), "RUNNING", 1000) == []
    assert decide(flags, snap(50), "COMPLETED", 2000) == ["finish"]


def test_mismatch_pauses_once_then_waits_for_the_pause():
    flags = {}
    assert decide(flags, snap(12, audits=(3, 1)), "RUNNING", 0) == ["pause"]
    flags["pauseRequested"] = True
    assert "pause" not in decide(flags, snap(12, audits=(3, 1)), "PAUSING", 10)
    assert decide(flags, snap(12, audits=(3, 1)), "PAUSED", 20) == ["finish"]
    assert decide({}, snap(5, quarantines=[["w", "r"]]), "RUNNING", 0) == ["pause"]


def test_no_event_before_its_generation_and_no_leave_without_join():
    assert decide({}, snap(30, [["c", 30, 1]]), "RUNNING", 0) == ["join", "fault"]
    assert "leave" not in decide({}, snap(35), "RUNNING", 0)
