import json

import pytest

from heteroes.runtime_info import JsonlLog, code_info, environment_info


def test_the_environment_says_where_and_with_what_a_run_happened():
    info = environment_info("cpu")

    assert {"hostname", "platform", "python", "torch", "numpy", "transformers", "device", "gpu_name"} <= set(info)
    assert info["device"] == "cpu" and info["gpu_name"] is None
    json.dumps(info)


def test_the_code_is_identified_by_its_commit_and_whether_the_tree_is_dirty():
    info = code_info()

    assert set(info) == {"git_commit", "git_dirty"}
    assert info["git_commit"] is None or len(info["git_commit"]) == 40
    assert info["git_dirty"] in (None, True, False)


def test_a_jsonl_log_writes_one_json_object_per_line_and_is_readable_while_it_is_written(tmp_path):
    log = JsonlLog(tmp_path / "events.jsonl")

    log({"event": "a", "n": 1})
    assert (tmp_path / "events.jsonl").read_text().splitlines() == ['{"event": "a", "n": 1}']       # flushed at once
    log({"event": "b"})
    log.close()

    assert [json.loads(line) for line in (tmp_path / "events.jsonl").read_text().splitlines()] == [{"event": "a", "n": 1}, {"event": "b"}]


def test_a_jsonl_log_never_overwrites_a_file(tmp_path):
    (tmp_path / "events.jsonl").write_text("evidence\n")

    with pytest.raises(FileExistsError):
        JsonlLog(tmp_path / "events.jsonl")

    assert (tmp_path / "events.jsonl").read_text() == "evidence\n"


def test_a_jsonl_log_can_be_called_from_several_threads_without_mixing_lines(tmp_path):
    import threading

    log = JsonlLog(tmp_path / "events.jsonl")
    threads = [threading.Thread(target=lambda i=i: [log({"event": "x", "thread": i, "pad": "p" * 200, "k": k}) for k in range(50)])
               for i in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    log.close()

    lines = (tmp_path / "events.jsonl").read_text().splitlines()
    assert len(lines) == 400 and all(json.loads(line)["event"] == "x" for line in lines)


def test_a_value_json_cannot_carry_is_a_type_error_and_the_log_stays_valid(tmp_path):
    log = JsonlLog(tmp_path / "events.jsonl")
    log({"event": "ok"})

    with pytest.raises(TypeError):
        log({"event": "bad", "value": object()})
    log.close()

    assert (tmp_path / "events.jsonl").read_text().splitlines() == ['{"event": "ok"}']


def test_a_log_can_be_continued_with_append_and_is_never_overwritten_without_it(tmp_path):
    from heteroes.runtime_info import JsonlLog
    path = tmp_path / "events.jsonl"
    log = JsonlLog(path)
    log({"n": 1})
    log.close()
    import pytest
    with pytest.raises(FileExistsError):
        JsonlLog(path)
    again = JsonlLog(path, append=True)
    again({"n": 2})
    again.close()
    assert path.read_text().splitlines() == ['{"n": 1}', '{"n": 2}']
