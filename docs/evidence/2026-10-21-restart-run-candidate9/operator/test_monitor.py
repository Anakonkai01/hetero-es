from monitor import JOINER, QUANG, WIN, decide

LEASE = [["c", 0, 1]]


def snap(applied, active=(), audits=(1, 0), quarantines=(), restarts=(), workers=None, membership=()):
    return {
        "applied": applied,
        "active": {w: LEASE for w in active},
        "audits": list(audits),
        "quarantines": list(quarantines),
        "restarts": list(restarts),
        "workers": workers or {},
        "membership": [list(m) for m in membership],
    }


def restarted(worker, t):
    return ["worker_restarted", worker, 1, t, None]


LEFT = [(JOINER, "JOIN", 3), (JOINER, "LEAVE", 9)]


def test_the_whole_sequence_happens_once_in_order_one_fault_at_a_time():
    flags = {"skipped": []}
    assert decide(flags, snap(1), "RUNNING", 0) == []
    assert decide(flags, snap(2), "RUNNING", 0) == ["join"]
    flags["joined"] = 1
    assert decide(flags, snap(5), "RUNNING", 10) == []  # Quang holds no lease
    assert decide(flags, snap(5, [QUANG, WIN]), "RUNNING", 10) == ["fault_quang"]
    flags.update(killedAt=100, qBase=7)
    # nothing else while Quang's restart is open, even with a Windows lease
    assert decide(flags, snap(7, [WIN], workers={QUANG: 7}), "RUNNING", 200) == []
    assert decide(flags, snap(7, restarts=[restarted(QUANG, 150)], workers={QUANG: 7}), "RUNNING", 200) == []
    back = [restarted(QUANG, 150)]
    assert decide(flags, snap(8, restarts=back, workers={QUANG: 8}), "RUNNING", 210) == ["verdict_quang", "leave"]
    flags.update(quangVerdict="recovered", left=210)
    q = {QUANG: 8}
    assert decide(flags, snap(9, restarts=back, workers=q), "RUNNING", 220) == []  # LEAVE not in the ledger yet
    assert decide(flags, snap(9, restarts=back, workers=q, membership=LEFT), "RUNNING", 230) == []  # not past it yet
    assert decide(flags, snap(10, restarts=back, workers=q, membership=LEFT), "RUNNING", 240) == ["rejoin"]
    flags.update(rejoinedAt=240, jBase=3)
    j = {QUANG: 8, JOINER: 3}
    assert decide(flags, snap(12, [WIN], restarts=back, workers=j, membership=LEFT), "RUNNING", 300) == []
    back2 = back + [restarted(JOINER, 260)]
    j2 = {QUANG: 8, JOINER: 4}
    assert decide(flags, snap(13, restarts=back2, workers=j2, membership=LEFT), "RUNNING", 310) == ["verdict_rejoin"]
    flags["rejoinVerdict"] = "recovered"
    assert decide(flags, snap(13, restarts=back2, workers=j2), "RUNNING", 320) == []  # Windows holds no lease
    assert decide(flags, snap(14, [WIN], restarts=back2, workers=j2), "RUNNING", 330) == ["fault_win"]
    flags.update(stoppedAt=330, winBase=5)
    assert decide(flags, snap(16, restarts=back2, workers=j2), "RUNNING", 569) == []
    assert decide(flags, snap(20, restarts=back2, workers=j2), "RUNNING", 570) == ["relaunch"]
    flags["relaunched"] = 570
    assert decide(flags, snap(21, restarts=back2, workers=j2), "RUNNING", 580) == ["contribution"]
    flags["contributionOn"] = 600
    w = {**j2, WIN: 5}
    early = snap(22, restarts=back2 + [restarted(WIN, 590)], workers={**w, WIN: 6})
    assert decide(flags, early, "RUNNING", 620) == []  # counted from contribution ON, not from the stop
    done = snap(23, restarts=back2 + [restarted(WIN, 610)], workers={**w, WIN: 6})
    assert decide(flags, done, "RUNNING", 630) == ["verdict_win"]
    flags["winVerdict"] = "recovered"
    assert decide(flags, done, "RUNNING", 640) == []
    assert decide(flags, snap(50), "COMPLETED", 1000) == ["finish"]


def test_a_restart_that_never_comes_is_a_verdict_and_the_next_fault_follows():
    flags = {"skipped": [], "joined": 1, "killedAt": 100, "qBase": 7}
    assert decide(flags, snap(10, workers={QUANG: 7}), "RUNNING", 699) == []
    assert decide(flags, snap(10, workers={QUANG: 7}), "RUNNING", 700) == ["verdict_quang", "leave"]
    flags = {
        "skipped": [],
        "joined": 1,
        "killedAt": 1,
        "qBase": 0,
        "quangVerdict": "failed",
        "left": 1,
        "rejoinedAt": 100,
        "jBase": 3,
    }
    assert decide(flags, snap(20, [WIN], workers={JOINER: 3}), "RUNNING", 699) == []
    assert decide(flags, snap(20, [WIN], workers={JOINER: 3}), "RUNNING", 700) == ["verdict_rejoin", "fault_win"]
    never = {"skipped": ["quang", "rejoin"], "joined": 1, "stoppedAt": 100, "relaunched": 340, "winBase": 5}
    assert decide(never, snap(30), "RUNNING", 939) == ["contribution"]
    assert decide(never, snap(30), "RUNNING", 940) == ["contribution", "verdict_win"]


def test_a_restart_counts_only_for_its_worker_after_its_fault_with_new_results():
    flags = {"skipped": [], "joined": 1, "killedAt": 450, "qBase": 7}
    assert "verdict_quang" not in decide(
        flags, snap(12, restarts=[restarted(QUANG, 100)], workers={QUANG: 9}), "RUNNING", 500
    )
    assert "verdict_quang" not in decide(
        flags, snap(12, restarts=[restarted(WIN, 470)], workers={QUANG: 9}), "RUNNING", 500
    )
    assert "verdict_quang" not in decide(
        flags, snap(12, restarts=[restarted(QUANG, 470)], workers={QUANG: 7}), "RUNNING", 500
    )
    deferred = [["worker_restart_deferred", QUANG, 1, 470, 409]]
    assert "verdict_quang" not in decide(flags, snap(12, restarts=deferred, workers={QUANG: 9}), "RUNNING", 500)


def test_an_event_that_cannot_happen_in_time_is_recorded_as_not_exercised():
    assert decide({"skipped": [], "joined": 1}, snap(20, [QUANG]), "RUNNING", 0) == ["skip_quang"]
    assert decide({"skipped": ["quang"], "joined": 1}, snap(30), "RUNNING", 0) == ["skip_rejoin"]
    assert decide({"skipped": ["quang"], "joined": 1}, snap(29), "RUNNING", 0) == ["leave"]
    left = {"skipped": ["quang"], "joined": 1, "left": 1}
    assert decide(left, snap(30, membership=LEFT), "RUNNING", 0) == ["skip_rejoin"]
    assert decide({"skipped": ["quang", "rejoin"], "joined": 1}, snap(36, [WIN]), "RUNNING", 0) == ["skip_win"]
    assert decide({"skipped": ["quang", "rejoin"], "joined": 1}, snap(35, [WIN]), "RUNNING", 0) == ["fault_win"]


def test_quang_is_not_killed_before_the_1660s_joined():
    assert decide({"skipped": []}, snap(6, [QUANG]), "RUNNING", 0) == ["join"]


def test_mismatch_pauses_once_then_waits_for_the_pause():
    flags = {"skipped": []}
    assert decide(flags, snap(12, audits=(3, 1)), "RUNNING", 0) == ["pause"]
    flags["pauseRequested"] = True
    assert "pause" not in decide(flags, snap(12, audits=(3, 1)), "PAUSING", 10)
    assert decide(flags, snap(12, audits=(3, 1)), "PAUSED", 20) == ["finish"]
    assert decide({"skipped": []}, snap(5, quarantines=[["w", "r"]]), "RUNNING", 0) == ["pause"]
