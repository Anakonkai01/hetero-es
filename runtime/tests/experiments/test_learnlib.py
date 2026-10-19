"""The helpers of the learning experiment (`artifacts/experiments/2026-10-07-learning-runtime/learnlib.py`): the held-out sets, the checkpoint rule, the verdict."""
import importlib.util
import os
from pathlib import Path

import pytest

PATH = Path(os.environ.get("LEARNLIB_PATH") or Path(__file__).resolve().parents[2] / "artifacts/experiments/2026-10-07-learning-runtime/learnlib.py")   # LEARNLIB_PATH: a mutant, for the mutation check
spec = importlib.util.spec_from_file_location("learnlib", PATH)
learnlib = importlib.util.module_from_spec(spec)
spec.loader.exec_module(learnlib)


def test_heldout_sets_have_the_size_and_share_no_question_with_the_training_set():
    train = {q for q, _ in learnlib.train_questions()}
    sets = learnlib.heldout_sets()

    assert set(sets) == {"H3", "H1", "H2"} and len(learnlib.train_questions()) == 64
    for name, qa in sets.items():
        assert len(qa) == 128 and not ({q for q, _ in qa} & train), name


def test_heldout_removal_of_a_training_question_keeps_the_size(monkeypatch):
    # force a collision: pretend the first held-out question of level 3 is a training question
    first = learnlib.make_questions(learnlib.HELDOUT_COUNT + 64, 3, learnlib.HELDOUT_SEED)[0][0]
    monkeypatch.setattr(learnlib, "train_questions", lambda: [(first, 0)])

    sets = learnlib.heldout_sets()

    assert len(sets["H3"]) == 128 and first not in {q for q, _ in sets["H3"]}


def test_heldout_sets_differ_from_each_other_and_are_deterministic():
    a, b = learnlib.heldout_sets(), learnlib.heldout_sets()

    assert a == b and a["H1"] != a["H2"] and a["H3"][0][0] != a["H1"][0][0]


def test_the_answers_of_the_heldout_sets_are_computed():
    for qa in learnlib.heldout_sets().values():
        assert all(isinstance(answer, int) for _, answer in qa)


@pytest.mark.parametrize("g,total,every,expected", [(4, 100, 5, True), (3, 100, 5, False), (99, 100, 5, True), (97, 98, 5, True), (96, 98, 5, False), (0, 1, 5, True)])
def test_keep_checkpoint_rule(g, total, every, expected):
    assert learnlib.keep_checkpoint(g, total, every) is expected


@pytest.mark.parametrize("args", [(-1, 10, 5), (10, 10, 5), (0, 0, 5), (0, 10, 0)])
def test_keep_checkpoint_refuses_nonsense(args):
    with pytest.raises(ValueError):
        learnlib.keep_checkpoint(*args)


def test_the_checkpoints_of_100_generations_are_20_plus_the_base():
    kept = [g for g in range(100) if learnlib.keep_checkpoint(g, 100, 5)]

    assert len(kept) == 20 and kept[0] == 4 and kept[-1] == 99


def test_summarize_decomposes_accuracy():
    ev = {"correct": [True, True, False, False], "answer_line": [True, False, False, False], "chars": [10, 20, 30, 40], "tokens": 7}
    s = learnlib.summarize(ev)

    assert s["accuracy"] == 0.5 and s["answer_line_rate"] == 0.25 and s["accuracy_with_line"] == 1.0 and s["mean_chars"] == 25 and s["correct"] == 2


def test_accuracy_with_line_is_none_when_no_reply_has_a_line():
    s = learnlib.summarize({"correct": [False], "answer_line": [False], "chars": [3], "tokens": 1})

    assert s["accuracy_with_line"] is None


def test_sign_test_p_values():
    assert learnlib.sign_test_p(0, 0) == 1.0
    assert learnlib.sign_test_p(10, 0) == pytest.approx(1 / 1024)
    assert learnlib.sign_test_p(5, 5) == pytest.approx(0.623046875)
    assert learnlib.sign_test_p(70, 30) < 1e-4


def summary(acc, line=0.5, cond=0.6):
    return {"accuracy": acc, "answer_line_rate": line, "accuracy_with_line": cond}


BASE = {"train": summary(0.3), "H3": summary(0.33), "H1": summary(0.6), "H2": summary(0.9)}


def final(train=0.5, h3=0.5, h1=0.6, h2=0.9, cond=0.6):
    return {"train": summary(train), "H3": summary(h3, cond=cond), "H1": summary(h1), "H2": summary(h2)}


def test_verdict_all_criteria_met():
    v = learnlib.verdict(BASE, final(), 80, 0.02, 100)

    assert (v["S1"], v["S2"], v["S3"], v["S4"], v["S5"]) == (True, True, True, True, True)
    assert "not explained by shorter replies" in v["label"]


@pytest.mark.parametrize("change,key", [({"h3": 0.33 + 7 / 128}, "S1"), ({"train": 0.39}, "S3"), ({"h1": 0.6 - 9 / 128}, "S4"), ({"h2": 0.9 - 9 / 128}, "S4")])
def test_each_threshold_is_exact(change, key):
    assert learnlib.verdict(BASE, final(**change), 80, 0.02, 100)[key] is False


def test_thresholds_are_inclusive_at_the_boundary():
    v = learnlib.verdict(BASE, final(h3=0.33 + 8 / 128, h1=0.6 - 8 / 128, h2=0.9 - 8 / 128, train=0.4), 70, 0.0001, 100)

    assert v["S1"] and v["S3"] and v["S4"] and v["S2"]


def test_s2_needs_both_the_count_and_a_positive_mean():
    assert learnlib.verdict(BASE, final(), 69, 0.02, 100)["S2"] is False
    assert learnlib.verdict(BASE, final(), 90, 0.0, 100)["S2"] is False
    assert learnlib.verdict(BASE, final(), 90, -0.01, 100)["S2"] is False


def test_s5_false_when_conditional_accuracy_drops_more_than_five_points():
    v = learnlib.verdict(BASE, final(cond=0.54), 80, 0.02, 100)

    assert v["S5"] is False and v["label"] == "a learning signal on this workload"


def test_labels_for_the_other_outcomes():
    assert learnlib.verdict(BASE, final(h3=0.33), 80, 0.02, 100)["label"].startswith("the direction carries information")
    assert learnlib.verdict(BASE, final(h3=0.33), 40, 0.0, 100)["label"] == "no evidence of learning in this experiment"


def write_events(path, events):
    with open(path, "ab") as file:
        for e in events:
            file.write((__import__("json").dumps(e) + "\n").encode())


def make_keeper(tmp_path, total=10, every=5):
    (tmp_path / "pub").mkdir(exist_ok=True)
    return learnlib.CheckpointKeeper(tmp_path / "events.jsonl", tmp_path / "pub", tmp_path / "ckpt", total, every)


def publish(tmp_path, sha, content=b"x"):
    (tmp_path / "pub" / f"{sha}.bin").write_bytes(content)


def test_keeper_links_the_base_and_the_chosen_generations_only(tmp_path):
    keeper = make_keeper(tmp_path)
    publish(tmp_path, "a0")
    write_events(tmp_path / "events.jsonl", [{"event": "listening", "initial_weights_sha256": "a0"}])
    keeper.poll()
    for g in range(10):
        publish(tmp_path, f"c{g}", f"w{g}".encode())
        write_events(tmp_path / "events.jsonl", [{"event": "weights_published", "generation": g, "child_sha256": f"c{g}"}])
        keeper.poll()

    assert sorted(keeper.kept) == [0, 5, 10] and keeper.kept[5] == "c4" and keeper.kept[10] == "c9"
    assert sorted(p.name for p in (tmp_path / "ckpt").iterdir()) == ["g000-a0.bin", "g005-c4.bin", "g010-c9.bin"]


def test_keeper_file_survives_the_deletion_of_the_published_one(tmp_path):
    keeper = make_keeper(tmp_path, total=5)
    publish(tmp_path, "c4", b"weights")
    write_events(tmp_path / "events.jsonl", [{"event": "weights_published", "generation": 4, "child_sha256": "c4"}])
    keeper.poll()
    (tmp_path / "pub" / "c4.bin").unlink()

    assert (tmp_path / "ckpt" / "g005-c4.bin").read_bytes() == b"weights"


def test_keeper_waits_for_a_file_that_is_not_published_yet(tmp_path):
    keeper = make_keeper(tmp_path, total=5)
    write_events(tmp_path / "events.jsonl", [{"event": "weights_published", "generation": 4, "child_sha256": "c4"}])
    keeper.poll()
    assert keeper.kept == {} and keeper.pending == [(5, "c4")]
    publish(tmp_path, "c4")
    keeper.poll()

    assert keeper.kept == {5: "c4"} and keeper.pending == []


def test_keeper_ignores_a_half_written_line_until_it_is_complete(tmp_path):
    keeper = make_keeper(tmp_path, total=5)
    publish(tmp_path, "c4")
    line = '{"event": "weights_published", "generation": 4, "child_sha256": "c4"}'
    with open(tmp_path / "events.jsonl", "ab") as file:
        file.write(line[:30].encode())
    keeper.poll()
    assert keeper.kept == {}
    with open(tmp_path / "events.jsonl", "ab") as file:
        file.write((line[30:] + "\n").encode())
    keeper.poll()

    assert keeper.kept == {5: "c4"}


def test_keeper_survives_a_missing_events_file_and_a_repeated_event(tmp_path):
    keeper = make_keeper(tmp_path, total=5)
    keeper.poll()
    publish(tmp_path, "c4")
    event = {"event": "weights_published", "generation": 4, "child_sha256": "c4"}
    write_events(tmp_path / "events.jsonl", [event, event])
    keeper.poll()

    assert keeper.kept == {5: "c4"} and keeper.pending == []


def test_heldout_questions_come_from_the_generator_with_the_heldout_seed():
    expected = learnlib.make_questions(learnlib.HELDOUT_COUNT, 1, learnlib.HELDOUT_SEED)

    assert learnlib.heldout_sets()["H1"] == expected                       # level 1 has no training question to remove: the generator's own first 128


def test_count_positive_does_not_count_zero():
    assert learnlib.count_positive([0.1, 0.0, -0.1, 0.2]) == 2


def test_a_new_keeper_after_a_restart_reads_the_old_events_without_failing(tmp_path):
    first = make_keeper(tmp_path, total=5)
    publish(tmp_path, "c4", b"weights")
    write_events(tmp_path / "events.jsonl", [{"event": "weights_published", "generation": 4, "child_sha256": "c4"}])
    first.poll()
    second = make_keeper(tmp_path, total=5)
    second.poll()

    assert second.kept == {5: "c4"} and (tmp_path / "ckpt" / "g005-c4.bin").read_bytes() == b"weights"


def test_keeper_knows_when_the_last_generation_is_done(tmp_path):
    keeper = make_keeper(tmp_path, total=3)
    write_events(tmp_path / "events.jsonl", [{"event": "generation_done", "generation": 1}])
    keeper.poll()
    assert keeper.finished is False
    write_events(tmp_path / "events.jsonl", [{"event": "generation_done", "generation": 2}])
    keeper.poll()

    assert keeper.finished is True
