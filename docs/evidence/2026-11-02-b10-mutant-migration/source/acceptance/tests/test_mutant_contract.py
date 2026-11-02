"""Every acceptance mutation must still reach exactly one real source guard after module moves."""

import ast
import json
from pathlib import Path


def test_all_mutation_targets_exist_match_once_and_produce_valid_python():
    root = Path(__file__).resolve().parents[2]
    checked = 0
    for config in sorted((root / "acceptance/mutants").glob("*.json")):
        for mutant in json.loads(config.read_text()):
            candidates = (root / mutant["file"], root / "runtime" / mutant["file"])
            target = next((path for path in candidates if path.is_file()), None)
            assert target is not None, (config.name, mutant["name"], mutant["file"])
            source = target.read_text()
            assert source.count(mutant["old"]) == 1, (config.name, mutant["name"], mutant["file"])
            ast.parse(source.replace(mutant["old"], mutant["new"], 1))
            checked += 1
    assert checked >= 137
