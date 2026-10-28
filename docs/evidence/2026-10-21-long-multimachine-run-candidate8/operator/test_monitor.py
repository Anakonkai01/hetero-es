from monitor import JOINER, LOCAL, QUANG, WIN, decide

LEASE = [["c", 0, 1]]


def snap(applied, active=(), audits=(1, 0), quarantines=(), restarts=(), workers=None, expired=None):
    return {"applied": applied, "active": {w: LEASE for w in active}, "audits": list(audits),
            "quarantines": list(quarantines), "restarts": list(restarts), "workers": workers or {},
            "expired": expired or {}}


def restarted(worker, t):
    return ["worker_restarted", worker, 1, t]


def test_the_whole_sequence_happens_once_and_in_order():
    flags = {"skipped": []}
    assert decide(flags, snap(9), "RUNNING", 0) == []
    assert decide(flags, snap(10), "RUNNING", 0) == ["join"]
    flags["joined"] = 1
    assert decide(flags, snap(14), "RUNNING", 100) == []  # no active lease on the Windows worker yet
    assert decide(flags, snap(14, [WIN]), "RUNNING", 100) == ["fault_win"]
    flags.update(stoppedAt=100, winBase=5)
    assert decide(flags, snap(16, [WIN]), "RUNNING", 339) == []
    assert decide(flags, snap(20), "RUNNING", 340) == ["relaunch"]
    flags["relaunched"] = 340
    assert decide(flags, snap(21), "RUNNING", 350) == ["contribution"]
    flags["contributionOn"] = 360
    # the app is back but nothing restarted it yet: nothing else may happen (no leave at g28)
    assert decide(flags, snap(28, workers={WIN: 5}), "RUNNING", 400) == []
    assert decide(flags, snap(28, restarts=[restarted(WIN, 380)], workers={WIN: 5}), "RUNNING", 400) == []
    ok = snap(28, restarts=[restarted(WIN, 380)], workers={WIN: 6})
    assert decide(flags, ok, "RUNNING", 420) == ["verdict_win", "leave"]
    flags.update(winVerdict="recovered", left=430)
    assert decide(flags, snap(31, [QUANG]), "RUNNING", 440) == []
    assert decide(flags, snap(32), "RUNNING", 450) == []  # Quang holds no lease
    assert decide(flags, snap(32, [QUANG], restarts=ok["restarts"], workers={WIN: 6}), "RUNNING", 450) == ["fault_quang"]
    flags.update(killedAt=450, qBase=7)
    assert decide(flags, snap(34, restarts=ok["restarts"]), "RUNNING", 500) == []
    done = snap(36, restarts=[restarted(WIN, 380), restarted(QUANG, 470)], workers={WIN: 9, QUANG: 8})
    assert decide(flags, done, "RUNNING", 520) == ["verdict_quang"]
    flags["quangVerdict"] = "recovered"
    assert decide(flags, snap(37, restarts=done["restarts"], workers=done["workers"]), "RUNNING", 530) == []
    assert decide(flags, snap(38, restarts=done["restarts"], workers=done["workers"]), "RUNNING", 540) == ["join2"]
    flags["joined2"] = 540
    assert decide(flags, snap(39, [LOCAL], restarts=done["restarts"], workers=done["workers"]), "RUNNING", 550) == []
    sig = snap(40, [LOCAL], restarts=done["restarts"], workers=done["workers"])
    assert decide(flags, sig, "RUNNING", 560) == ["sigstop"]
    flags.update(sigAt=560, expBase=0)
    assert decide(flags, snap(41, expired={LOCAL: 1}), "RUNNING", 739) == []  # 179 s
    assert decide(flags, snap(41, expired={LOCAL: 0}), "RUNNING", 745) == []  # long enough, but no expiry row yet
    assert decide(flags, snap(41, expired={LOCAL: 1}), "RUNNING", 740) == ["sigcont"]
    flags["contAt"] = 740
    assert decide(flags, snap(50), "COMPLETED", 1000) == ["finish"]


def test_a_stop_is_never_left_frozen_beyond_the_maximum():
    flags = {"skipped": [], "sigAt": 1, "expBase": 0}
    assert "sigcont" not in decide(flags, snap(41), "RUNNING", 300)
    assert "sigcont" in decide(flags, snap(41), "RUNNING", 301)


def test_a_restart_that_never_comes_is_a_verdict_not_a_stall():
    flags = {"skipped": [], "joined": 1, "stoppedAt": 100, "relaunched": 340, "contributionOn": 360, "winBase": 5}
    assert decide(flags, snap(30, workers={WIN: 5}), "RUNNING", 959) == []
    assert decide(flags, snap(30, workers={WIN: 5}), "RUNNING", 960) == ["verdict_win", "leave"]  # the run goes on
    flags2 = {"skipped": [], "joined": 1, "stoppedAt": 100, "relaunched": 340, "winBase": 5}  # the app never came back
    assert decide(flags2, snap(30), "RUNNING", 939) == ["contribution"]
    assert decide(flags2, snap(30), "RUNNING", 940) == ["contribution", "verdict_win", "leave"]


def test_an_event_that_cannot_happen_in_time_is_recorded_as_not_exercised():
    assert "skip_win" in decide({"skipped": []}, snap(24), "RUNNING", 0)
    flags = {"skipped": ["win"], "joined": 1}
    assert decide(flags, snap(40), "RUNNING", 0) == ["leave", "skip_quang"]
    flags["skipped"].append("quang")
    flags["left"] = 1
    assert decide(flags, snap(44, [LOCAL]), "RUNNING", 0) == ["skip_join2"]
    flags["skipped"].append("join2")
    assert decide(flags, snap(44, [LOCAL]), "RUNNING", 0) == ["skip_sig"]
    assert decide(flags, snap(41, [LOCAL]), "RUNNING", 0) == ["sigstop"]


def test_mismatch_pauses_once_then_waits_for_the_pause():
    flags = {"skipped": []}
    assert decide(flags, snap(12, audits=(3, 1)), "RUNNING", 0) == ["pause"]
    flags["pauseRequested"] = True
    assert "pause" not in decide(flags, snap(12, audits=(3, 1)), "PAUSING", 10)
    assert decide(flags, snap(12, audits=(3, 1)), "PAUSED", 20) == ["finish"]
    assert decide({"skipped": []}, snap(5, quarantines=[["w", "r"]]), "RUNNING", 0) == ["pause"]


def test_nothing_before_its_generation_and_no_leave_without_join():
    assert decide({"skipped": []}, snap(30, [WIN, QUANG, LOCAL]), "RUNNING", 0) == ["join", "fault_win"]
    assert "leave" not in decide({"skipped": ["win"]}, snap(35), "RUNNING", 0)


def test_each_step_waits_for_the_one_before():
    base = {"skipped": [], "joined": 1, "left": 1}
    # Quang is not killed while the Windows restart is still open, even with a lease at g32
    waiting = {**base, "stoppedAt": 100, "relaunched": 340, "contributionOn": 360, "winBase": 5}
    assert "fault_quang" not in decide(waiting, snap(33, [QUANG], workers={WIN: 5}), "RUNNING", 400)
    done = {"skipped": ["win"], "joined": 1}
    assert "fault_quang" in decide(done, snap(33, [QUANG]), "RUNNING", 400)
    # the second JOIN needs the first LEAVE and a resolved Quang restart
    killed = {"skipped": ["win"], "joined": 1, "left": 1, "killedAt": 450, "qBase": 7}
    assert "join2" not in decide(killed, snap(38, workers={QUANG: 7}), "RUNNING", 460)
    assert "join2" in decide(killed, snap(38, restarts=[restarted(QUANG, 470)], workers={QUANG: 8}), "RUNNING", 520)
    never_left = {"skipped": ["win", "quang"], "joined": 1}
    assert "join2" not in decide(never_left, snap(38), "RUNNING", 0)
    # the freeze needs an active lease on the 5070 worker (g40+) and the second JOIN done or not exercised
    ready = {"skipped": ["win", "quang"], "joined": 1, "left": 1, "joined2": 1}
    assert "sigstop" not in decide(ready, snap(40), "RUNNING", 0)
    assert "sigstop" in decide(ready, snap(40, [LOCAL]), "RUNNING", 0)
    assert "sigstop" not in decide({**ready, "joined2": 0}, snap(40, [LOCAL]), "RUNNING", 0)


def test_a_restart_event_from_before_the_kill_does_not_count():
    flags = {"skipped": ["win"], "joined": 1, "left": 1, "killedAt": 450, "qBase": 7}
    old = snap(36, restarts=[restarted(QUANG, 100)], workers={QUANG: 9})
    assert "verdict_quang" not in decide(flags, old, "RUNNING", 500)
    other = snap(36, restarts=[restarted(WIN, 470)], workers={QUANG: 9})
    assert "verdict_quang" not in decide(flags, other, "RUNNING", 500)
