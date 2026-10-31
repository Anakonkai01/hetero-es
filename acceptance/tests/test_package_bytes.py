"""The package probe binds runtime bytes to committed source, while documentation may be edited."""

import io
from pathlib import Path
import subprocess
import tarfile
import zipfile

import pytest

from acceptance.probes.package_bytes import verify_packages


def archive(path, files):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(path, "w:gz") as stream:
        for name, data in files.items():
            item = tarfile.TarInfo(name)
            item.size = len(data)
            stream.addfile(item, io.BytesIO(data))


@pytest.fixture
def package(tmp_path):
    repo, build = tmp_path / "repo", tmp_path / "build"
    repo.mkdir()
    source = repo / "runtime/src/heteroes/__init__.py"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"VALUE = 1\n")
    (repo / "docs").mkdir()
    (repo / "docs/note.md").write_text("original\n")
    (repo / "runtime/docs").mkdir()
    (repo / "runtime/docs/note.md").write_text("original\n")
    (repo / "README.md").write_text("original\n")
    for args in (
        ["init", "-q"],
        ["add", "."],
        ["-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-qm", "source"],
    ):
        subprocess.run(["git", *args], cwd=repo, check=True)
    archive(
        build / "worker/linux-unpacked/resources/worker/runtime.tar.gz",
        {"src/heteroes/__init__.py": source.read_bytes()},
    )
    wheel = io.BytesIO()
    with zipfile.ZipFile(wheel, "w") as stream:
        stream.writestr("heteroes/__init__.py", source.read_bytes())
    archive(
        build / "server/linux-unpacked/resources/server/runtime.tar.gz", {"web/notebooks/sdk.whl": wheel.getvalue()}
    )
    return repo, build


def test_committed_runtime_packages_match(package):
    repo, build = package
    assert verify_packages(build, repo) == 1


def test_documentation_edits_and_new_receipts_do_not_invalidate_runtime_bytes(package):
    repo, build = package
    for name in ("docs/note.md", "runtime/docs/note.md", "README.md", "docs/new-receipt.json"):
        (repo / name).write_text("changed\n")
    assert verify_packages(build, repo) == 1


@pytest.mark.parametrize("name", ["runtime/src/heteroes/__init__.py", "runtime/src/heteroes/new.py"])
def test_modified_or_untracked_source_is_refused(package, name):
    repo, build = package
    (repo / name).write_text("VALUE = 2\n")
    with pytest.raises(ValueError, match="source tree is not clean"):
        verify_packages(build, repo)


@pytest.mark.parametrize("target", ["worker", "server"])
def test_package_byte_differences_are_refused_even_on_a_clean_source_tree(package, target):
    repo, build = package
    if target == "worker":
        archive(build / "worker/linux-unpacked/resources/worker/runtime.tar.gz", {"src/heteroes/__init__.py": b"wrong"})
    else:
        wheel = io.BytesIO()
        with zipfile.ZipFile(wheel, "w") as stream:
            stream.writestr("heteroes/__init__.py", b"wrong")
        archive(
            build / "server/linux-unpacked/resources/server/runtime.tar.gz", {"web/notebooks/sdk.whl": wheel.getvalue()}
        )
    with pytest.raises(ValueError, match="differs"):
        verify_packages(build, repo)


def test_server_archive_must_contain_exactly_one_sdk_wheel(package):
    repo, build = package
    archive(build / "server/linux-unpacked/resources/server/runtime.tar.gz", {})
    with pytest.raises(ValueError, match="expected one SDK wheel"):
        verify_packages(build, repo)
