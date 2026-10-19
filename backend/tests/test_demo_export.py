"""The demo run published on the home page is anonymous and complete enough to replay."""

import importlib.util
import json
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "export-demo-run.py"
spec = importlib.util.spec_from_file_location("export_demo_run", SCRIPT)
export = importlib.util.module_from_spec(spec)
spec.loader.exec_module(export)
RUN = json.loads((Path(__file__).parent / "fixtures" / "run-d09d6ea8.json").read_text())


def test_the_exported_run_has_no_ids_hashes_or_names_beyond_hardware_labels():
    timeline = export.export_timeline(RUN["body"], RUN["snapshot"])
    text = json.dumps(timeline)
    for secret in (
        RUN["body"]["experimentId"],
        RUN["body"]["name"],
        RUN["body"].get("workspaceId", "lab-unlikely-token"),
        "seed",
    ):
        assert secret not in text, secret
    assert not any(
        len(token) >= 32 and all(c in "0123456789abcdef" for c in token)
        for token in text.replace('"', " ").replace(",", " ").split()
    )
    assert timeline["experiment"]["name"] == "Demo run" and timeline["experiment"]["id"] == "demo"
    assert {w["id"] for w in timeline["workers"]} == {"5070ti", "3060", "3060-thao"}


def test_it_still_replays_completely():
    timeline = export.export_timeline(RUN["body"], RUN["snapshot"])
    assert (
        timeline["experiment"]["status"] == "COMPLETED" and timeline["nowMs"] == timeline["experiment"]["completedMs"]
    )
    assert len(timeline["jobs"]) == 36 and all(j["endMs"] for j in timeline["jobs"])
    assert [g["status"] for g in timeline["generations"]] == ["COMPLETED"] * 3
    assert {m["type"] for m in timeline["marks"]} <= export.KEEP_MARKS
    assert all("detail" not in m for m in timeline["marks"])


def test_the_file_is_small_enough_to_ship_with_the_website():
    assert len(json.dumps(export.export_timeline(RUN["body"], RUN["snapshot"]), separators=(",", ":"))) < 30_000
