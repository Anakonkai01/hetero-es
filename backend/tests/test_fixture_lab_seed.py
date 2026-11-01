"""Browser fixture seeders survive additive schema columns, and startup failures fail the overall check command."""

import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[2]


def test_browser_fixture_finished_and_stuck_seeders_use_the_current_schema(lab):
    spec = importlib.util.spec_from_file_location("browser_fixture_seed", ROOT / "scripts/serve-test-lab.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    client, store, runtime, administrator = lab
    recorded = json.loads((ROOT / "backend/tests/fixtures/run-d09d6ea8.json").read_text())
    finished = module.load_run(store, recorded)
    assert store.get(finished)["experimentId"] == finished
    assert store.get(finished)["ownerUserId"] == "admin"
    stuck = module.load_stuck_run(store, recorded)
    assert store.get(stuck)["status"] == "STARTING"
    with store.db() as db:
        assert (
            db.execute("SELECT count(*) FROM assignments WHERE run_id=:p0 AND released=0", (stuck,)).fetchone()[0] == 1
        )
        assert db.execute("SELECT count(*) FROM monitoring_events").fetchone()[0] == 1


def test_check_all_cannot_report_success_when_a_browser_fixture_never_starts(tmp_path):
    repo, commands = tmp_path / "fixture-repo", tmp_path / "commands"
    commands.mkdir()
    for name in ("scripts", "runtime", "frontend", "desktop/worker", "desktop/server"):
        (repo / name).mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ROOT / "scripts/check-all.sh", repo / "scripts/check-all.sh")
    bodies = {
        "python-fixture": '#!/bin/sh\ncase "$*" in *serve-test-lab.py*) echo fixture-startup-failed >&2; exit 1;; esac\nexit 0\n',
        "node": "#!/bin/sh\nexit 0\n",
        "npx": "#!/bin/sh\nexit 0\n",
        "npm": "#!/bin/sh\nexit 0\n",
        "xvfb-run": "#!/bin/sh\nexit 0\n",
        "curl": "#!/bin/sh\nexit 1\n",
        "sleep": "#!/bin/sh\nexit 0\n",
        "seq": '#!/bin/sh\nprintf "1\\n"\n',
    }
    for name, body in bodies.items():
        path = commands / name
        path.write_text(body)
        path.chmod(0o700)
    output = repo / "checks"
    completed = subprocess.run(
        ["bash", str(repo / "scripts/check-all.sh"), str(output)],
        env={
            **os.environ,
            "PATH": str(commands) + os.pathsep + os.environ["PATH"],
            "PYTHON": str(commands / "python-fixture"),
            "RUFF": "/bin/true",
            "RUNTIME_PYTHON": "/bin/true",
        },
        capture_output=True,
        text=True,
    )
    assert completed.returncode != 0 and "ALL PASS" not in completed.stdout
    assert "fixture-lab-" in completed.stdout
    logs = list(output.glob("lab-*.log"))
    assert len(logs) == 7 and all("fixture-startup-failed" in path.read_text() for path in logs)
