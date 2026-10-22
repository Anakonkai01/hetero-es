#!/usr/bin/env python3
"""Build Linux unpacked apps in an isolated source copy; never publish or replace profiles."""

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True, help="fresh directory for workspace and unpacked apps")
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[1]
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    work = out / "workspace"
    work.mkdir()
    candidates = (
        subprocess.check_output(["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"], cwd=repo)
        .decode()
        .split("\0")
    )
    for name in set(candidates):
        if not name:
            continue
        allowed = name.startswith(("backend/", "desktop/", "frontend/", "packages/", "scripts/", "runtime/src/"))
        allowed = allowed or name in (
            "package.json",
            "package-lock.json",
            "runtime/scripts/run_worker.py",
            "runtime/pyproject.toml",
            "runtime/notebooks/researcher.ipynb",
        )
        source = repo / name
        if not allowed or not source.is_file():
            continue
        target = work / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    environment = {**os.environ, "CUDA_VISIBLE_DEVICES": ""}
    environment.pop("ELECTRON_RUN_AS_NODE", None)

    def run(argv, cwd=work, env=environment):
        print("CHECK", " ".join(str(a) for a in argv[:4]), flush=True)
        subprocess.run([str(a) for a in argv], cwd=cwd, env=env, check=True)

    run(["npm", "ci", "--ignore-scripts"])
    run(["npm", "run", "build:web"])
    sdk = work / "frontend/dist/notebooks"
    sdk.mkdir()
    shutil.copyfile(work / "runtime/notebooks/researcher.ipynb", sdk / "researcher.ipynb")
    run(
        [
            os.environ.get("RUNTIME_PYTHON", str(Path.home() / "miniforge3/envs/heteroes-match/bin/python")),
            "-m",
            "pip",
            "wheel",
            "--no-deps",
            "--no-build-isolation",
            "-q",
            "-w",
            sdk,
            work / "runtime",
        ]
    )
    run([sys.executable, "-I", work / "scripts/refresh-worker-runtime.py", "--track-a", work / "runtime"])
    run([sys.executable, "-I", work / "scripts/refresh-server-runtime.py", "--web", work / "frontend/dist"])
    receipt = {
        "sourceCommit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip(),
        "linuxOnly": True,
        "published": False,
        "apps": [],
    }
    for app, executable in [("worker", "heteroes-worker"), ("server", "heteroes-server")]:
        run(["npm", "run", "build", "--workspace", "@heteroes/" + app])
        run(
            [
                "npx",
                "electron-builder",
                "--linux",
                "dir",
                "--x64",
                "--publish",
                "never",
                "--config.directories.output=" + str(out / app),
            ],
            cwd=work / "desktop" / app,
        )
        unpacked = out / app / "linux-unpacked"
        archive = unpacked / "resources/app.asar"
        code = (
            "const path=require('node:path');const root=process.argv[1];"
            "const shared=path.join(root,'node_modules/@heteroes/desktop-shared');"
            "const common=require(path.join(shared,'runtime.cjs'));"
            "const download=require(path.join(shared,'download.cjs'));"
            "const setup=require(path.join(root,'electron/setup.cjs'));"
            "if(typeof common.run!=='function'||typeof common.extract!=='function'||"
            "typeof download.verifiedDownload!=='function'||typeof setup.Setup!=='function')process.exit(2);"
        )
        run([unpacked / executable, "-e", code, archive], env={**environment, "ELECTRON_RUN_AS_NODE": "1"})
        receipt["apps"].append({"app": app, "unpacked": str(unpacked), "sharedModulesImport": True})
    (out / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
