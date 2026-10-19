import importlib.util
import json
from pathlib import Path
import sys

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "mutation-check.py"


@pytest.fixture(scope="module")
def tool():
    spec = importlib.util.spec_from_file_location("mutation_check_script", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def project(tmp_path):
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "tests").mkdir()
    (repo / "src" / "price.py").write_text("def total(a, b):\n    return a + b\n\n\ndef unused():\n    return 1\n")
    (repo / "tests" / "test_price.py").write_text(
        "from price import total\n\n\ndef test_total():\n    assert total(2, 3) == 5\n"
    )
    return repo


def arguments(project, tmp_path, mutants):
    (tmp_path / "mutants.json").write_text(json.dumps(mutants))
    return [
        "--repo",
        str(project),
        "--copy",
        "src",
        "--copy",
        "tests",
        "--env",
        "PYTHONPATH=src",
        "--test",
        f"{sys.executable} -m pytest -q -p no:cacheprovider tests",
        "--mutants",
        str(tmp_path / "mutants.json"),
        "--scratch",
        str(tmp_path),
    ]


def test_a_killed_mutant_gives_status_zero_and_the_repository_is_untouched(tool, project, tmp_path, capsys):
    before = (project / "src" / "price.py").read_text()
    code = tool.main(
        arguments(project, tmp_path, [{"name": "M1 minus", "file": "src/price.py", "old": "a + b", "new": "a - b"}])
    )
    out = capsys.readouterr().out
    assert code == 0 and "killed" in out and "control ok" in out and "1 of 1 mutants killed" in out
    assert (project / "src" / "price.py").read_text() == before
    assert not list(tmp_path.glob("mutation-*"))  # scratch copies are removed


def test_a_surviving_mutant_gives_status_one(tool, project, tmp_path, capsys):
    code = tool.main(
        arguments(
            project, tmp_path, [{"name": "M2 dead code", "file": "src/price.py", "old": "return 1", "new": "return 2"}]
        )
    )
    assert code == 1 and "SURVIVED" in capsys.readouterr().out


def test_a_failing_control_stops_before_any_mutant(tool, project, tmp_path, capsys):
    (project / "tests" / "test_price.py").write_text("def test_total():\n    assert False\n")
    code = tool.main(
        arguments(project, tmp_path, [{"name": "M3", "file": "src/price.py", "old": "a + b", "new": "a - b"}])
    )
    out = capsys.readouterr().out
    assert code == 1 and "CONTROL FAILED" in out and "M3" not in out


def test_an_ambiguous_or_missing_old_text_is_an_error_not_a_pass(tool, project, tmp_path):
    for old in ("return", "text that is not there"):
        with pytest.raises(ValueError, match="exactly once"):
            tool.main(arguments(project, tmp_path, [{"name": "M4", "file": "src/price.py", "old": old, "new": "x"}]))
