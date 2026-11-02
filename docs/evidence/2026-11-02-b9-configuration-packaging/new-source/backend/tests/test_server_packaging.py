"""A source bundle must retain recursive backend modules and PostgreSQL schema, excluding tests."""

import json
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile


def test_refreshed_server_archive_contains_recursive_code_and_database_resources(tmp_path):
    root = Path(__file__).resolve().parents[2]
    shutil.copytree(root / "backend", tmp_path / "backend", ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copytree(root / "runtime/src", tmp_path / "runtime/src", ignore=shutil.ignore_patterns("__pycache__"))
    resources = tmp_path / "desktop/server/resources"
    resources.mkdir(parents=True)
    shutil.copyfile(root / "desktop/server/resources/profile.json", resources / "profile.json")
    (tmp_path / "scripts").mkdir()
    shutil.copyfile(root / "scripts/refresh-server-runtime.py", tmp_path / "scripts/refresh-server-runtime.py")
    web = tmp_path / "web"
    web.mkdir()
    (web / "index.html").write_text("<title>Packaging fixture</title>")
    completed = subprocess.run(
        [sys.executable, "-I", str(tmp_path / "scripts/refresh-server-runtime.py"), "--web", str(web)],
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    with tarfile.open(resources / "runtime.tar.gz") as archive:
        names = set(archive.getnames())
    assert {
        "backend/apps/factory.py",
        "backend/repositories/observability.py",
        "backend/db/postgres_schema.sql",
        "web/index.html",
    } <= names
    assert not any("tests" in Path(name).parts or "__pycache__" in Path(name).parts for name in names)
    profile = json.loads((resources / "profile.json").read_text())
    before = json.loads((root / "desktop/server/resources/profile.json").read_text())
    assert profile["platforms"] == before["platforms"]
