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
        if "pytest" in check.command or check.name.startswith("strict-gpu-suite") or check.profile == "mutation":
            assert check.min_passed is not None and check.min_passed > 0, check.name
            if check.gpu:
                assert check.max_skipped == 0, check.name
    by_name = {check.name: check for check in CHECKS}
    assert by_name["strict-gpu-suite"].min_passed >= 1639
    assert by_name["strict-gpu-suite-native"].min_passed >= 956


def test_gpu_suites_supply_real_model_and_explicit_hardware_selection():
    from acceptance.hosts import LOCAL, WSL, NATIVE

    assert LOCAL.pytest_marks == ""
    assert WSL.pytest_marks == NATIVE.pytest_marks == "not sm120"
    assert WSL.pytest_min_passed == {"strict-gpu-suite": 1560}
    for check in CHECKS:
        if check.name.startswith("strict-gpu-suite"):
            assert "{repo}/acceptance/probes/pytest_gpu_suite.py" in check.command
            assert ("--models", "{models}") == check.command[
                check.command.index("--models") : check.command.index("--models") + 2
            ]
            assert ("-m", "{pytest_marks}") == check.command[-2:]


def test_only_architecture_specific_execution_cases_have_sm120_marker():
    import ast

    expected = {
        "test_integer_tma.py": {
            "test_tma_projection_matches_streamed_projection_bits",
            "test_tma_projection_reports_the_same_flags",
            "test_ineligible_calls_keep_the_streamed_route",
            "test_two_captured_launches_reusing_one_host_template_keep_their_own_tensors",
            "test_host_template_cache_stays_bounded_across_layout_changes",
        },
        "test_attention_key_stages.py": {
            "test_key_stages_match_the_original_bits_and_flags",
            "test_packed_batch_of_ragged_owners_matches_original",
            "test_opt_in_shared_stage_replays_with_changed_live_query",
        },
    }
    actual = {}
    for path in (REPO / "runtime/tests").rglob("*.py"):
        marked = {
            node.name
            for node in ast.parse(path.read_text()).body
            if isinstance(node, ast.FunctionDef)
            and any(ast.unparse(decorator) == "pytest.mark.sm120" for decorator in node.decorator_list)
        }
        if marked:
            actual[path.name] = marked
    assert actual == expected
