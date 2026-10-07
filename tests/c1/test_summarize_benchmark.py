"""`scripts/summarize_benchmark.py` on small synthetic runs written by hand: the headline is the steady-state T (generation 0 left out),
the intervals are over runs, and the policy is stored under its own key."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import summarize_benchmark as sb  # noqa: E402


def write_run(root, name, generation_seconds, policy="greedy", rewards=((0.1, 0.2),) * 4, final="aa"):
    run = root / name
    (run / "coordinator").mkdir(parents=True)
    (run / "run.json").write_text(json.dumps({"outcome": "ok"}))
    generations = [{"total_seconds": t, "wait_seconds": t - 1, "update_seconds": 0.5, "publish_seconds": 0.1,
                    "rewards": list(rewards[i]), "child_sha256": f"h{i}"} for i, t in enumerate(generation_seconds)]
    (run / "coordinator" / "summary.json").write_text(json.dumps({
        "generations": generations, "final_weights_sha256": final, "internal_errors": 0, "args": {"policy": policy}}))
    events = [{"event": "worker_start", "args": {"chunk": 1}, "environment": {"gpu_name": "G"}}]
    for i in range(2):
        events.append({"event": "step", "kind": "COMMITTED", "candidate_id": f"x/g0/c{i}", "timing": {"total": 1.0}, "step_seconds": 1.2})
    (run / "worker-fast.jsonl").write_text("\n".join(json.dumps(e) for e in events) + "\n")
    return run


def test_t_steady_leaves_out_generation_zero_and_is_the_headline(tmp_path, capsys):
    # B0: generation 0 is 100 s, the others 100 s. B3: generation 0 is FAST (no sync yet: 60 s), the others 100 s.
    for k, extra in enumerate((0.0, 0.0, 0.0), start=1):
        write_run(tmp_path, f"n8-B0-r{k}", [100.0, 100.0 + extra, 100.0, 100.0])
        write_run(tmp_path, f"n8-B3-r{k}", [60.0, 100.0 + extra, 100.0, 100.0])
    out = tmp_path / "summary.json"
    assert sb.main([str(tmp_path), "--out", str(out)]) == 0
    capsys.readouterr()
    conditions = json.loads(out.read_text())["conditions"]

    b3 = conditions["n8-B3"]
    assert b3["T_mean"] == pytest.approx(90.0)                       # with generation 0: looks 10 % faster than B0
    assert b3["T_steady"] == pytest.approx(100.0)                    # steady state: not faster at all
    assert conditions["n8-B0"]["cluster_benefit_vs_B0"] == pytest.approx(1.0)
    assert b3["cluster_benefit_vs_B0"] == pytest.approx(100.0 / 90.0)
    assert b3["cluster_benefit_steady"] == pytest.approx(1.0)


def test_the_interval_is_over_runs_and_contains_the_truth_when_runs_are_noisy(tmp_path, capsys):
    # B0 steady means of the three runs: 100, 110, 90 ; B3: 100, 100, 100 -> CB = 1.0 with a wide interval
    for k, steady in enumerate((100.0, 110.0, 90.0), start=1):
        write_run(tmp_path, f"n8-B0-r{k}", [steady] * 4)
        write_run(tmp_path, f"n8-B3-r{k}", [100.0] * 4)
    out = tmp_path / "summary.json"
    sb.main([str(tmp_path), "--out", str(out)])
    capsys.readouterr()
    b3 = json.loads(out.read_text())["conditions"]["n8-B3"]
    assert b3["cluster_benefit_steady"] == pytest.approx(1.0)
    assert b3["cluster_benefit_steady_ci95"] > 0.1          # three noisy runs cannot claim a small gain
    assert len(b3["T_steady_runs"]) == 3


def test_a_single_generation_run_has_no_steady_state(tmp_path, capsys):
    write_run(tmp_path, "n8-B0-r1", [100.0], rewards=((0.1, 0.2),))
    out = tmp_path / "summary.json"
    sb.main([str(tmp_path), "--out", str(out)])
    capsys.readouterr()
    entry = json.loads(out.read_text())["conditions"]["n8-B0"]
    assert "T_steady" not in entry
    assert entry["T_mean"] == 100.0


def test_the_policy_has_its_own_key(tmp_path):
    run = write_run(tmp_path, "n8-B2-r1", [10.0, 10.0, 10.0], policy="proportional")
    summary = sb.summarize_run(run)
    assert summary["policy"] == "proportional"
    assert "chunks" not in summary
