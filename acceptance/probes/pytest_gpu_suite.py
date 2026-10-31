"""Prepare an isolated revision-named Qwen copy, then collect/run the GPU suite with that pinned model."""

import argparse
import json
import os
from pathlib import Path
import shutil


def prepare_model_view(models, out):
    from heteroes.catalog import PINNED_REVISION

    source = (Path(models) / "qwen").resolve()
    for name in ("config.json", "model.safetensors"):
        if not (source / name).is_file():
            raise FileNotFoundError(f"Missing pinned Qwen model file: {name}")
    out = Path(out).resolve()
    view = out / PINNED_REVISION
    out.mkdir(parents=True, exist_ok=False)
    # Independent files: an HF loader or a test can never write through to the owner's retained model.
    shutil.copytree(source, view)
    (out / "model-view.json").write_text(
        json.dumps({"revision": PINNED_REVISION, "source": str(source), "view": str(view)}, indent=2) + "\n"
    )
    return view


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--models", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("pytest_args", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    tests = args.pytest_args[1:] if args.pytest_args[:1] == ["--"] else args.pytest_args
    if not tests:
        parser.error("pass pytest arguments after --")
    view = prepare_model_view(args.models, args.out)
    os.environ["HETEROES_QWEN_PINNED_PATH"] = str(view)
    import pytest

    return pytest.main(tests)


if __name__ == "__main__":
    raise SystemExit(main())
