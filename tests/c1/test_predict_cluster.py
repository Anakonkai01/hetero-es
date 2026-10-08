"""`scripts/predict_cluster.py`: the prediction of a generation for any set of machines, with a remote worker catching up by download or by replay. Fake profiles, known numbers."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import predict_cluster as pc  # noqa: E402


def profile(worker_id, seconds, update=None, sync=None):
    return {"worker_id": worker_id, "candidate_times": {"64": {"total_median": seconds}}, "update": update, "sync": sync}


UPDATE = {"seconds_per_candidate_median": 0.1, "fixed_seconds": 0.0, "publish_seconds": 1.0, "hash_seconds": 0.5}


def write(tmp_path, name, content):
    path = tmp_path / name
    path.write_text(json.dumps(content), encoding="utf-8")
    return str(path)


@pytest.fixture
def files(tmp_path):
    return {
        "fast": write(tmp_path, "fast.json", profile("fast", 4.0, UPDATE)),
        "slow": write(tmp_path, "slow.json", profile("slow", 16.0, {**UPDATE, "seconds_per_candidate_median": 0.5}, {"total_seconds": 10.0})),
        "nosync": write(tmp_path, "nosync.json", profile("third", 8.0, {**UPDATE, "seconds_per_candidate_median": 0.2})),
        "syncfile": write(tmp_path, "sync.json", {"sync": {"total_seconds": 400.0}}),
    }


def test_the_first_worker_is_local_and_the_others_pay_their_synchronization(files):
    models = pc.build_models([files["fast"], files["slow"]], {}, 64, 24)

    assert [(m.worker_id, m.candidate_seconds, m.sync_seconds) for m, _ in models] == [("fast", 4.0, 0.0), ("slow", 16.0, 10.0)]


def test_replay_replaces_the_download_by_the_estimate_of_one_replay(files):
    models = pc.build_models([files["fast"], files["nosync"] + ":replay"], {}, 64, 24)

    third = models[1][0]
    assert third.sync_seconds == pytest.approx(24 * 0.2 + 0.5)          # update per candidate x N + the check of the hash; fixed 0


def test_a_missing_sync_block_is_completed_from_a_measure_sync_file_and_is_an_error_without_it(files):
    with pytest.raises(ValueError, match="synchronization"):
        pc.build_models([files["fast"], files["nosync"]], {}, 64, 24)
    models = pc.build_models([files["fast"], files["nosync"]], {"third": json.loads(Path(files["syncfile"]).read_text())}, 64, 24)
    assert models[1][0].sync_seconds == 400.0


def test_an_unknown_option_and_a_replay_without_the_update_cost_are_refused(files, tmp_path):
    with pytest.raises(ValueError, match="only ':replay'"):
        pc.build_models([files["fast"], files["slow"] + ":fast"], {}, 64, 24)
    bare = write(tmp_path, "bare.json", profile("bare", 8.0))
    with pytest.raises(ValueError, match="update cost"):
        pc.build_models([files["fast"], bare + ":replay"], {}, 64, 24)


def test_every_subset_with_the_local_worker_is_predicted_and_alone_has_benefit_one(files):
    models = pc.build_models([files["fast"], files["slow"], files["nosync"] + ":replay"], {}, 64, 24)

    result = pc.predict(models, 24, 0.05)

    assert set(result) == {"fast", "fast+slow", "fast+third", "fast+slow+third"}
    assert result["fast"]["B3_GREEDY_DYNAMIC"]["cluster_benefit_against_local_alone"] == pytest.approx(1.0)
    assert result["fast"]["B3_GREEDY_DYNAMIC"]["admit_by_the_threshold"] is False        # the same time is not under 95 percent of itself


def test_a_machine_that_costs_400_seconds_to_synchronize_does_not_help_and_by_replay_it_does(files):
    download = pc.predict(pc.build_models([files["fast"], files["nosync"]], {"third": {"sync": {"total_seconds": 400.0}}}, 64, 24), 24, 0.05)
    replay = pc.predict(pc.build_models([files["fast"], files["nosync"] + ":replay"], {}, 64, 24), 24, 0.05)

    assert download["fast+third"]["B3_GREEDY_DYNAMIC"]["cluster_benefit_against_local_alone"] <= 1.0 + 1e-9
    assert replay["fast+third"]["B3_GREEDY_DYNAMIC"]["cluster_benefit_against_local_alone"] > 1.1
    assert replay["fast+third"]["B3_GREEDY_DYNAMIC"]["admit_by_the_threshold"] is True


def test_the_local_profile_must_have_the_update_cost(tmp_path, files):
    bare = write(tmp_path, "bare.json", profile("bare", 4.0))
    with pytest.raises(ValueError, match="update cost"):
        pc.predict(pc.build_models([bare, files["slow"]], {}, 64, 24), 24, 0.05)


def test_an_existing_output_is_never_overwritten(files, tmp_path):
    out = tmp_path / "prediction.json"
    out.write_text("{}")
    assert pc.main(["--worker", files["fast"], "--candidates", "24", "--chunk", "64", "--out", str(out)]) == 2
