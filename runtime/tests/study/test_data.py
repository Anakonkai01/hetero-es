import json
import pytest
from heteroes.study.data import dataset, parse, batch, verify


def fixture():
    return {"all": {"format": "json", "content": json.dumps([{"q": f"Question {i}", "a": str(i)} for i in range(20)])}}


def test_seeded_split_and_frozen_batch_are_reproducible_without_global_rng():
    a = dataset(fixture(), mapping={"prompt": "q", "answer": "a"})
    assert a == dataset(fixture(), mapping={"prompt": "q", "answer": "a"})
    assert [len(a["splits"][name]) for name in ("train", "validation", "test")] == [16, 2, 2]
    assert batch(a, 0, 8, 11) == batch(a, 0, 8, 11)
    assert batch(a, 0, 8, 11) != batch(a, 1, 8, 11)
    a["splits"]["test"][0]["answer"] = "wrong"
    with pytest.raises(ValueError, match="hash"):
        verify(a)


def test_mappings_formats_and_gsm8k_exact_answers():
    assert parse("question,result\nCompute,1.00\n", "csv", {"prompt": "question", "answer": "result"}) == [
        {"prompt": "Compute", "answer": "1"}
    ]
    assert (
        parse('{"prompt":"Compute","answer":"Reasoning #### 1,200"}\n', "jsonl", adapter="gsm8k-v1")[0]["answer"]
        == "1200"
    )
    with pytest.raises(ValueError):
        parse('[{"prompt":"Compute","answer":true}]', "json")


def test_pre_split_preserves_official_test_and_rejects_leakage():
    files = {
        name: {"format": "json", "content": json.dumps([{"prompt": name, "answer": 0}])}
        for name in ("train", "validation", "test")
    }
    d = dataset(files)
    assert d["splits"]["test"] == [{"prompt": "test", "answer": "0"}]
    files["validation"] = files["test"]
    with pytest.raises(ValueError, match="Duplicate"):
        dataset(files)
