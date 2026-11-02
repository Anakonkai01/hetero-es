"""The shim-removal proof must reject altered assertions, calls and ordinary string values."""

import importlib.util
from pathlib import Path

import pytest


def proof():
    path = Path(__file__).resolve().parents[2] / "scripts/check-test-imports-only.py"
    spec = importlib.util.spec_from_file_location("test_import_proof", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.assert_imports_only


def test_direct_and_multiline_imports_can_move_without_changing_assertions():
    before = "from old import (\n    first,\n    second,\n)\nassert first() == second\n"
    after = "from new import first\nfrom other import second\nassert first() == second\n"
    proof()(before, after)


def test_child_python_command_can_change_only_its_embedded_imports():
    before = 'code = "from old import first; import sys; assert first() == sys.version"\n'
    after = 'code = "from new import first; import sys; assert first() == sys.version"\n'
    proof()(before, after)


@pytest.mark.parametrize(
    "after",
    [
        "from new import first\nassert first() != 1\n",
        "from new import first\nassert first() == 2\n",
        "from new import first\nassert other() == 1\n",
        "from new import first\n",
        "from new import first\nassert first() == 1\nprint('extra')\n",
    ],
)
def test_proof_rejects_any_non_import_behavior_change(after):
    with pytest.raises(ValueError):
        proof()("from old import first\nassert first() == 1\n", after)


def test_proof_rejects_changes_inside_embedded_assertions_or_ordinary_strings():
    with pytest.raises(ValueError):
        proof()(
            'code = "from old import first; assert first() == 1"\n',
            'code = "from new import first; assert first() == 2"\n',
        )
    with pytest.raises(ValueError):
        proof()('from old import first\nvalue = "expected"\n', 'from new import first\nvalue = "weakened"\n')


def test_proof_rejects_changes_on_non_import_lines_even_when_ast_is_unchanged():
    with pytest.raises(ValueError):
        proof()("from old import first\nassert first() == 1\n", "from new import first\nassert first() == 0x1\n")
