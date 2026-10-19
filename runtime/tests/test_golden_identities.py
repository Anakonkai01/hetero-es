"""
The identities that past runs recorded must still come out of the code: recipe hashes, workload hashes, generation record
hashes and the coefficients of every recorded update.

The fixture (`fixtures/golden-identities.json`) is built by `scripts/build_golden_identities.py` from `runtime/artifacts/` and
`docs/evidence/`; it holds the hashes the runs WROTE, not hashes computed by this code, so a refactor that changes how any of
them is made fails here. Rebuild it only when new evidence is added, never to make this test pass.
"""

import json
from pathlib import Path

import pytest

from heteroes.eval.workloads import get_workload
from heteroes.generation_record import GenerationRecord
from heteroes.manifest import WORKLOAD_NAMES, Recipe

FIXTURE = Path(__file__).parent / "fixtures" / "golden-identities.json"


@pytest.fixture(scope="module")
def golden():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def recipes_by_hash(golden):
    return {entry["recorded_hashes"][0]: Recipe.from_dict(entry["recipe"]) for entry in golden["recipes"]}


def test_the_fixture_covers_every_workload_and_links_every_record_to_a_recorded_recipe(golden, recipes_by_hash):
    # premise: without this the other tests could pass on an empty or partial fixture
    assert all(len(entry["recorded_hashes"]) == 1 for entry in golden["recipes"])
    assert {recipe.workload_name for recipe in recipes_by_hash.values()} == set(WORKLOAD_NAMES)
    assert len(golden["records"]) >= 400
    assert all(record["recipe_hash"] in recipes_by_hash for record in golden["records"])


def test_every_recorded_recipe_still_has_its_recorded_hash(golden):
    for entry in golden["recipes"]:
        recipe = Recipe.from_dict(entry["recipe"])
        assert recipe.hash == entry["recorded_hashes"][0], entry["sources"][0]
        assert recipe.to_dict() == entry["recipe"]


def test_every_recorded_workload_still_has_its_recorded_hash(recipes_by_hash):
    for recipe in recipes_by_hash.values():
        assert get_workload(recipe.workload_name).hash() == recipe.workload_hash, recipe.workload_name


def test_every_recorded_generation_record_still_has_its_recorded_hash_and_text(golden):
    for entry in golden["records"]:
        record = GenerationRecord.from_json(entry["record_json"])
        assert record.hash == entry["record_hash"], entry["sources"][0]
        assert record.to_json() == entry["record_json"], entry["sources"][0]


def test_every_recorded_update_still_has_the_coefficients_of_its_rewards(golden, recipes_by_hash):
    for entry in golden["records"]:
        record = GenerationRecord.from_json(entry["record_json"])
        record.verify_coefficients(recipes_by_hash[entry["recipe_hash"]].reward_eta)
