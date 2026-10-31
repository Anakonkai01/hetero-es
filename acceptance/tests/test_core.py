"""The acceptance model must never let a gate pass without evidence, nor hide a deferral or a failure."""

import json
import subprocess
import sys

import pytest

from acceptance import core
from acceptance.core import Check, Gate, Host

PY = sys.executable


def registry():
    checks = [
        Check("unit", "cpu", (PY, "-c", "print('ok')")),
        Check("gpu-suite", "gpu", (PY, "-c", "pass"), hosts=("local", "3060-wsl"), gpu=True),
    ]
    gates = [Gate(f"{m}.x", m, "something", checks=("unit",)) for m in core.MILESTONES]
    return checks, gates


def test_a_consistent_registry_is_accepted():
    core.validate(*registry())


@pytest.mark.parametrize(
    "gate, message",
    [
        (Gate("M1.y", "M1", "t", deferred="later"), "reason"),
        (Gate("M1.y", "M1", "t", open="  todo  "), "reason"),
        (Gate("M1.y", "M1", "t", checks=("unit",), deferred="no hardware of that kind here"), "exactly one"),
        (Gate("M1.y", "M1", "t"), "exactly one"),
        (Gate("M1.y", "M1", "t", checks=("missing",)), "unknown check"),
        (Gate("M1.y", "M1", "t", checks=("unit@3060-wsl",)), "does not run"),
        (Gate("M2.y", "M1", "t", checks=("unit",)), "milestone"),
        (Gate("M1.x", "M1", "t", checks=("unit",)), "duplicate"),
    ],
)
def test_inconsistent_gates_are_refused(gate, message):
    checks, gates = registry()
    with pytest.raises(ValueError, match=message):
        core.validate(checks, [*gates, gate])


def test_every_milestone_needs_a_gate():
    checks, gates = registry()
    with pytest.raises(ValueError, match="M6"):
        core.validate(checks, [g for g in gates if g.milestone != "M6"])


def test_unknown_profile_is_refused():
    checks, gates = registry()
    with pytest.raises(ValueError, match="profile"):
        core.validate([*checks, Check("x", "fast", ("true",))], gates)


def run(check, tmp_path, runner=subprocess.run):
    return core.run_check(check, Host("local", PY), tmp_path, tmp_path, runner=runner)


def test_passing_check_records_a_hashed_log(tmp_path):
    result = run(Check("a", "cpu", (PY, "-c", "print('hello')"), expect="hello"), tmp_path)
    assert result.status == core.PASS and result.returncode == 0
    log = (tmp_path / "a" / "output.log").read_bytes()
    assert b"hello" in log and result.log_sha256 == __import__("hashlib").sha256(log).hexdigest()


@pytest.mark.parametrize(
    "command, expect, detail",
    [
        ((PY, "-c", "raise SystemExit(3)"), "", "exit status 3"),
        ((PY, "-c", "print('FAILED: x')"), "ALL PASS", "expected output"),
        (("/nonexistent/binary",), "", "could not start"),
    ],
)
def test_failures_are_failures(tmp_path, command, expect, detail):
    result = run(Check("a", "cpu", command, expect=expect), tmp_path)
    assert result.status == core.FAIL and detail in result.detail


def test_timeout_is_a_failure_not_a_pass(tmp_path):
    result = run(Check("a", "cpu", (PY, "-c", "import time; time.sleep(5)"), timeout=1), tmp_path)
    assert result.status == core.FAIL and result.returncode is None and "timed out" in result.detail


def test_cpu_checks_hide_the_gpu_and_gpu_checks_keep_it(tmp_path, monkeypatch):
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "0")
    code = "import os; print('cvd=' + repr(os.environ.get('CUDA_VISIBLE_DEVICES')))"
    run(Check("cpu", "cpu", (PY, "-c", code)), tmp_path)
    run(Check("gpu", "gpu", (PY, "-c", code), gpu=True), tmp_path)
    assert "cvd=''" in (tmp_path / "cpu" / "output.log").read_text()
    assert "cvd='0'" in (tmp_path / "gpu" / "output.log").read_text()


def test_placeholders_expand_per_host(tmp_path):
    check = Check("a", "cpu", ("{runtime_python}", "-c", "import sys; print(sys.argv)", "{models}", "{out}"))
    result = core.run_check(check, Host("h", PY, models="/models/x"), tmp_path, tmp_path)
    text = (tmp_path / "a" / "output.log").read_text()
    assert result.status == core.PASS and "/models/x" in text and str(tmp_path / "a") in text


def receipt(tree, finished, results, dirty=False):
    return {"format": core.RECEIPT_FORMAT, "tree": tree, "dirty": dirty, "finished": finished, "host": "local",
            "profiles": ["cpu"], "results": results}  # fmt: skip


def result(name, status, host="local"):
    return {"name": name, "host": host, "status": status}


def test_merge_keeps_only_the_same_clean_tree_and_the_latest_result():
    receipts = [
        receipt("t1", "2026-10-27T10:00:00", [result("unit", core.FAIL)]),
        receipt("t1", "2026-10-27T11:00:00", [result("unit", core.PASS)]),
        receipt("t0", "2026-10-27T12:00:00", [result("unit", core.FAIL), result("old", core.PASS)]),
        receipt("t1", "2026-10-27T13:00:00", [result("gpu-suite", core.PASS)], dirty=True),
    ]
    merged = core.merge(receipts, "t1")
    assert merged == {("unit", "local"): result("unit", core.PASS)}


def test_gate_status_needs_every_named_result():
    gates = [
        Gate("M1.a", "M1", "t", checks=("unit", "gpu-suite@3060-wsl")),
        Gate("M1.b", "M1", "t", checks=("unit",)),
        Gate("M2.a", "M2", "t", checks=("unit", "gpu-suite")),
        Gate("M3.a", "M3", "t", deferred="needs a Turing GPU, none is available"),
        Gate("M4.a", "M4", "t", open="integration into the worker is not written yet"),
    ]
    merged = {("unit", "local"): result("unit", core.PASS), ("gpu-suite", "local"): result("gpu-suite", core.FAIL)}
    rows = {g.id: (s, r, e) for g, s, r, e in core.evaluate(gates, merged)}
    assert rows["M1.a"][0] == core.NOT_RUN and ("gpu-suite@3060-wsl", core.NOT_RUN) in rows["M1.a"][2]
    assert rows["M1.b"][0] == core.PASS
    assert rows["M2.a"][0] == core.FAIL
    assert rows["M3.a"][:2] == (core.DEFERRED, "needs a Turing GPU, none is available")
    assert rows["M4.a"][:2] == (core.OPEN, "integration into the worker is not written yet")


def test_milestone_status_orders_failures_first_and_lists_deferrals():
    gates = [
        Gate("M0.a", "M0", "t", checks=("unit",)),
        Gate("M0.b", "M0", "t", deferred="needs a full disk, deferred by the owner"),
        Gate("M1.a", "M1", "t", checks=("unit",)),
        Gate("M1.b", "M1", "t", open="the outbox recovery test is not written"),
        Gate("M1.c", "M1", "t", checks=("other",)),
    ]
    merged = {("unit", "local"): result("unit", core.PASS), ("other", "local"): result("other", core.FAIL)}
    status = core.milestone_status(core.evaluate(gates, merged))
    assert status["M0"] == "PASS (with deferred gates)" and status["M1"] == core.FAIL
    assert status["M2"] == core.PASS  # no gates at all in this partial list: validate() refuses that registry


def test_report_prints_reasons_and_receipts():
    gates = [Gate("M0.b", "M0", "disk", deferred="needs a full disk, deferred by the owner")]
    text = core.report(core.evaluate(gates, {}), "t1", [receipt("t1", "2026-10-27T10:00", [])])
    assert "needs a full disk, deferred by the owner" in text and "**DEFERRED**" in text and "local cpu" in text


def test_write_and_load_receipt_round_trip(tmp_path):
    path = tmp_path / "r.json"
    core.write_receipt(path, tree="t", dirty=False, commit="c", host="local", profiles=["cpu"], results=[], started="s")
    assert core.load_receipts([path])[0]["tree"] == "t"
    path.write_text(json.dumps({"format": "other"}))
    with pytest.raises(ValueError):
        core.load_receipts([path])


def git(repo, *args):
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", *args], cwd=repo, check=True, capture_output=True
    )


def test_source_identity_ignores_docs_and_sees_source_changes(tmp_path):
    git(tmp_path, "init", "-q")
    (tmp_path / "docs").mkdir()
    (tmp_path / "a.py").write_text("x = 1\n")
    (tmp_path / "docs" / "n.md").write_text("one\n")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-q", "-m", "1")
    first, dirty = core.source_tree(tmp_path)
    assert first.startswith("src-") and not dirty
    (tmp_path / "docs" / "n.md").write_text("two\n")
    (tmp_path / "docs" / "receipt.json").write_text("{}\n")
    assert core.source_tree(tmp_path) == (first, False)
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-q", "-m", "2")
    assert core.source_tree(tmp_path) == (first, False)
    (tmp_path / "b.py").write_text("y = 2\n")
    assert core.source_tree(tmp_path) == (first, True)
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-q", "-m", "3")
    second, dirty = core.source_tree(tmp_path)
    assert second != first and not dirty


def test_staged_copy_reports_the_controller_identity(tmp_path):
    (tmp_path / "SOURCE_TREE").write_text("src-abc\n")
    assert core.source_tree(tmp_path) == ("src-abc", False)


@pytest.mark.parametrize(
    "summary,expected",
    [
        ("10 passed in 0.1s", core.PASS),
        ("10 passed, 1 skipped in 0.1s", core.FAIL),
        ("10 skipped in 0.1s", core.FAIL),
        ("9 passed in 0.1s", core.FAIL),
        ("no pytest summary", core.FAIL),
        ("10 passed, 1 failed in 0.1s", core.FAIL),
    ],
)
def test_pytest_checks_enforce_positive_counts_and_skip_limit(tmp_path, summary, expected):
    check = Check("suite", "gpu", (PY, "-c", f"print({summary!r})"), min_passed=10, max_skipped=0)
    result = run(check, tmp_path)
    assert result.status == expected
    assert result.pytest_summary == (summary if " in " in summary else "")
    if expected == core.PASS:
        assert result.counts["passed"] == 10 and result.counts["skipped"] == 0


def test_mutation_counts_are_from_control_not_from_killed_mutants(tmp_path):
    output = "control ok    | 20 passed in 0.1s\nkilled test | 1 failed, 19 passed in 0.1s\n1 of 1 mutants killed."
    result = run(Check("mutation", "mutation", (PY, "-c", f"print({output!r})"), min_passed=20), tmp_path)
    assert result.status == core.PASS and result.counts["passed"] == 20
    assert result.counts.get("failed", 0) == 0


def test_pytest_counts_accept_colored_summaries_and_deselections():
    counts, summary = core.pytest_counts("noise\n\x1b[32m=== 12 passed, 3 deselected, 1 warning in 0.2s ===\x1b[0m\n")
    assert counts["passed"] == 12 and counts["deselected"] == 3 and counts["warnings"] == 1
    assert counts["skipped"] == 0 and "12 passed" in summary


@pytest.mark.parametrize("minimum,passed,expected", [(12, 11, core.FAIL), (8, 9, core.PASS)])
def test_host_specific_executed_test_floor_is_enforced(tmp_path, minimum, passed, expected):
    host = Host("sm86", PY, pytest_marks="not sm120", pytest_min_passed={"suite": minimum})
    check = Check(
        "suite", "gpu", (PY, "-c", f"print('{passed} passed, 79 deselected in 0.1s')"), min_passed=10, max_skipped=0
    )
    result = core.run_check(check, host, tmp_path, tmp_path)
    assert result.status == expected
    assert core.expand("{pytest_marks}", host, tmp_path, tmp_path) == "not sm120"
    assert result.counts["deselected"] == 79


def test_result_keeps_relative_log_summary_counts_and_last_fifty_lines(tmp_path):
    output = "\n".join([str(i) for i in range(75)] + ["10 passed in 0.1s"])
    result = run(Check("suite", "cpu", (PY, "-c", f"print({output!r})"), min_passed=1), tmp_path)
    assert result.log == "suite/output.log"
    assert len(result.log_tail) == 50 and result.log_tail[-1] == "10 passed in 0.1s"
    assert result.log_tail[0] == "26"
    target = tmp_path / "receipt.json"
    core.write_receipt(
        target, tree="t", dirty=False, commit="c", host="local", profiles=["cpu"], results=[result], started="s"
    )
    stored = json.loads(target.read_text())["results"][0]
    assert stored["counts"]["passed"] == 10 and stored["pytest_summary"] == "10 passed in 0.1s"
    assert len(stored["log_tail"]) == 50


def test_source_identity_excludes_runtime_docs_and_root_markdown_including_renames(tmp_path):
    git(tmp_path, "init", "-q")
    (tmp_path / "runtime/docs").mkdir(parents=True)
    (tmp_path / "runtime/src").mkdir()
    (tmp_path / "runtime/docs/n.md").write_text("old docs")
    (tmp_path / "README.md").write_text("readme")
    (tmp_path / "runtime/src/a.py").write_text("old code")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-q", "-m", "baseline")
    first, _ = core.source_tree(tmp_path)
    (tmp_path / "runtime/docs/n.md").write_text("new docs")
    (tmp_path / "AGENTS.md").write_text("instructions")
    (tmp_path / "README.md").write_text("new readme")
    assert core.source_tree(tmp_path) == (first, False)
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-q", "-m", "documentation")
    assert core.source_tree(tmp_path) == (first, False)
    git(tmp_path, "mv", "runtime/docs/n.md", "runtime/docs/renamed.md")
    assert core.source_tree(tmp_path) == (first, False)
    git(tmp_path, "commit", "-q", "-m", "move docs")
    git(tmp_path, "mv", "runtime/docs/renamed.md", "runtime/src/now-source.md")
    assert core.source_tree(tmp_path) == (first, True)
    git(tmp_path, "commit", "-q", "-m", "source moved from docs")
    second, dirty = core.source_tree(tmp_path)
    assert first != second and dirty is False
    assert core.source_tree(tmp_path, "HEAD~1") == (first, False)
    (tmp_path / "runtime/src/a.py").write_text("new code")
    assert core.source_tree(tmp_path) == (second, True)
