"""The real registry is consistent, and every script, golden file and mutant group it names exists."""

from pathlib import Path
import json

from acceptance import core
from acceptance.hosts import HOSTS
from acceptance.registry import CHECKS, GATES

REPO = Path(__file__).resolve().parents[2]


def test_registry_is_valid_and_covers_every_milestone():
    core.validate(CHECKS, GATES)
    assert {g.milestone for g in GATES} == set(core.MILESTONES)


def test_every_check_host_is_configured():
    assert {h for c in CHECKS for h in c.hosts} <= set(HOSTS)


def test_every_named_file_exists():
    for check in CHECKS:
        for part in check.command:
            path = part.replace("{repo}/", "")
            if path.startswith(("acceptance/", "scripts/")) and " " not in path:
                assert (REPO / path).exists(), (check.name, path)
            if path.startswith("tests/eval/"):
                assert (REPO / "runtime" / path).exists(), (check.name, path)


def test_golden_files_are_well_formed():
    golden = json.loads((REPO / "acceptance/golden/strict-b22.json").read_text())
    assert set(golden["models"]) == {"qwen", "smol", "tiny"}
    assert [c["state"] for c in golden["models"]["qwen"]["cases"]] == ["parent", "plus", "minus", "restored"]
    throughput = json.loads((REPO / "acceptance/golden/throughput.json").read_text())
    assert set(throughput["tokensSha256"]) == {"short32", "chat128"}
    for mutants in (REPO / "acceptance/mutants").glob("*.json"):
        assert all({"name", "file", "old", "new"} <= set(m) for m in json.loads(mutants.read_text()))


def test_pytest_and_mutation_checks_cannot_pass_without_executed_tests():
    for check in CHECKS:
        if "pytest" in check.command or check.profile == "mutation":
            assert check.min_passed is not None and check.min_passed > 0, check.name
            if check.gpu:
                assert check.max_skipped == 0, check.name
    by_name = {check.name: check for check in CHECKS}
    assert by_name["strict-gpu-suite"].min_passed >= 1599
    assert by_name["strict-gpu-suite-native"].min_passed >= 1035
