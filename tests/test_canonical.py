import hashlib

import pytest

from heteroes.canonical import canonical_json_bytes, canonical_json_hash


def test_bytes_match_the_hand_written_canonical_form():
    # keys sorted, no spaces, non-ASCII escaped: written out by hand
    assert canonical_json_bytes({"b": [1, 2], "a": "é"}) == b'{"a":"\\u00e9","b":[1,2]}'


def test_hash_is_the_sha256_of_those_bytes():
    obj = {"b": [1, 2], "a": "é"}

    assert canonical_json_hash(obj) == hashlib.sha256(b'{"a":"\\u00e9","b":[1,2]}').hexdigest()


def test_the_order_of_the_keys_does_not_matter_but_the_order_of_a_list_does():
    assert canonical_json_hash({"x": 1, "y": 2}) == canonical_json_hash({"y": 2, "x": 1})
    assert canonical_json_hash([1, 2]) != canonical_json_hash([2, 1])


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_values_that_are_not_json_are_refused(bad):
    with pytest.raises(ValueError):
        canonical_json_bytes({"value": bad})
