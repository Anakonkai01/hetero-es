"""CPU-only provenance and handoff checks; never import the numerical runtime or torch."""

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess


ROOT = Path(__file__).resolve().parents[4]
EVIDENCE = ROOT / "docs/evidence"
SUFFIXES = (
    "prefill-warp-m",
    "newton-cycles",
    "mma-order",
    "attention-head-tiles",
    "attention-key-stages",
    "tma-host-maps",
    "request-cache-context",
    "qkv-attention-fusion",
)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    assert not args.out.exists(), "Use a fresh receipt path"

    selected = "0eb86cb948878fe430049882b80b3a5ad74730ba"
    control = EVIDENCE / "2026-10-27-strict-tma-pipeline/raw/full-base-a.json"
    expected_tokens = {c["case"]: c["tokensSha256"] for c in json.loads(control.read_text())["cases"]}
    report = {
        "status": "ok",
        "selectedRuntime": selected,
        "gpuExecution": False,
        "selectedSourceControl": str(control.relative_to(ROOT)),
        "experiments": [],
    }
    documents = []
    scanned = []
    for suffix in SUFFIXES:
        folder = EVIDENCE / f"2026-10-27-strict-{suffix}"
        seal_path = folder / "seal-01.json"
        seal = json.loads(seal_path.read_text())
        assert seal["selected"] is False and seal["runtimeCommit"] == selected[:8]
        files = {
            p.relative_to(folder).as_posix(): p
            for p in folder.rglob("*")
            if p.is_file() and "__pycache__" not in p.parts and ".pytest_cache" not in p.parts and p != seal_path
        }
        assert set(files) == set(seal["filesSha256"]), suffix
        assert "What this does NOT show" in (folder / "README.md").read_text()
        entry = {"name": suffix, "sealedFiles": len(files), "pythonSources": 0, "jsonFiles": 0, "pilotCases": 0}
        for name, path in files.items():
            data = path.read_bytes()
            assert sha(data) == seal["filesSha256"][name], (suffix, name)
            scanned.append(path)
            if path.suffix == ".py":
                compile(data, str(path), "exec")
                entry["pythonSources"] += 1
            elif path.suffix == ".json":
                value = json.loads(data)
                entry["jsonFiles"] += 1
                if not isinstance(value, dict):
                    continue  # Mutation specifications are valid top-level JSON lists.
                for probe, digest in value.get("probeHashes", {}).items():
                    assert sha((folder / "harness" / probe).read_bytes()) == digest, (suffix, probe)
                for case in value.get("cases", []):
                    if "tokensSha256" in case:
                        assert case["tokensSha256"] == expected_tokens[case["case"]], (suffix, case["case"])
                        entry["pilotCases"] += 1
        if suffix in ("attention-head-tiles", "attention-key-stages"):
            helper = "head_tiles.py" if suffix == "attention-head-tiles" else "stages.py"
            operator = json.loads((folder / "raw/operators-01.json").read_text())
            assert operator["sourceSha256"] == sha((folder / "harness" / helper).read_bytes())
        documents.append(folder / "README.md")
        report["experiments"].append(entry)

    runtime_files = git("ls-tree", "-r", "--name-only", selected, "runtime/src").decode().splitlines()
    for relative in runtime_files:
        assert (ROOT / relative).read_bytes() == git("show", f"{selected}:{relative}"), relative
    assert not git("ls-files", "--others", "--exclude-standard", "runtime/src").strip()
    report["unchangedRuntimeFiles"] = len(runtime_files)

    handoff = ROOT / "docs/handoff-claude-after-codex-perf-2026-10-27.md"
    current = ROOT / "docs/HANDOFF.md"
    documents.extend((handoff, current))
    checked_links = 0
    for document in documents:
        source = document.read_text()
        if document == current:
            source = source.split("## Tóm tắt cho chủ dự án (2026-10-27)", 1)[1].split(
                "## Tóm tắt trước đó (2026-10-26)", 1
            )[0]
        for target in re.findall(r"\]\(([^)]+)\)", source):
            target = target.split("#", 1)[0]
            if not target or "://" in target:
                continue
            assert (document.parent / target).exists(), (document.name, target)
            checked_links += 1
    report["localLinksChecked"] = checked_links
    report["documentSha256"] = {str(p.relative_to(ROOT)): sha(p.read_bytes()) for p in documents}

    credential_patterns = (
        re.compile(rb"-----BEGIN (?:[A-Z]+ )?PRIVATE KEY-----"),
        re.compile(rb"\bBearer\s+[A-Za-z0-9_.~+/-]{20,}", re.I),
        re.compile(rb"\b(?:password|passwd|sudo_password|ssh_password)\s*[:=]\s*['\"]?[^\s'\";,]+", re.I),
    )
    scanned.extend(documents)
    for path in scanned:
        assert not any(p.search(path.read_bytes()) for p in credential_patterns), (
            "Possible credential pattern; inspect privately",
            path.relative_to(ROOT).as_posix(),
        )
    report["credentialPatternFilesChecked"] = len(set(scanned))
    report["limits"] = "Provenance/syntax/docs checks only; no new GPU execution, acceptance or performance claim."
    with args.out.open("x") as stream:
        json.dump(report, stream, indent=2)
        stream.write("\n")
    print(json.dumps({"status": "ok", "experiments": len(SUFFIXES), "unchangedRuntimeFiles": len(runtime_files)}))


if __name__ == "__main__":
    main()
