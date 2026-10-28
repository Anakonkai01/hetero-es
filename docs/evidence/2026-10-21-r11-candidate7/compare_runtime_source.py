"""Compare every file in the candidate7 runtime archives with the repository source, byte for byte.

Worker archive paths map to runtime/<path>. Server archive paths: backend/* -> backend/*
(the server ships only the shared modules its backend imports), heteroes/* ->
runtime/src/heteroes/*, web/* -> <build>/web/*. Also checks that the packaged resources (Linux and Windows
unpacked) equal the committed desktop resources. Usage: python3 -I compare_runtime_source.py <repo> <build dir>
"""

import hashlib
import json
import sys
import tarfile
from pathlib import Path


def sha(data):
    return hashlib.sha256(data).hexdigest()


def compare(archive, mapping):
    files, differing, missing = [], [], []
    with tarfile.open(archive) as tar:
        for member in tar.getmembers():
            if not member.isfile():
                continue
            source = mapping(member.name)
            data = tar.extractfile(member).read()
            files.append(member.name)
            if not source.is_file():
                missing.append(member.name)
            elif source.read_bytes() != data:
                differing.append(member.name)
    return files, differing, missing


def backend_imports(repo):
    """Every heteroes module the packaged backend imports (the server ships only these shared modules)."""
    import ast

    names = set()
    for source in (repo / "backend").glob("*.py"):
        for node in ast.walk(ast.parse(source.read_text())):
            if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("heteroes"):
                names.add(node.module)
            elif isinstance(node, ast.Import):
                names.update(a.name for a in node.names if a.name.startswith("heteroes"))
    return {n for n in names if (repo / "runtime/src" / (n.replace(".", "/") + ".py")).is_file()}


def main(repo, build):
    repo, build = Path(repo), Path(build)
    result = {}
    worker_archive = repo / "desktop/worker/resources/runtime.tar.gz"
    files, differing, missing = compare(worker_archive, lambda name: repo / "runtime" / name)
    result["worker"] = {
        "runtimeSha256": sha(worker_archive.read_bytes()),
        "comparedFiles": len(files),
        "allBytesEqual": not differing and not missing,
        "differing": differing,
        "missing": missing,
        "membershipModulePresent": "src/heteroes/product/membership.py" in files,
        "files": files,
    }

    def server_source(name):
        if name.startswith("heteroes/"):
            return repo / "runtime/src" / name
        if name.startswith("web/"):
            return build / name
        return repo / name

    server_archive = repo / "desktop/server/resources/runtime.tar.gz"
    files, differing, missing = compare(server_archive, server_source)
    result["server"] = {
        "runtimeSha256": sha(server_archive.read_bytes()),
        "comparedFiles": len(files),
        "pythonFiles": sum(name.endswith(".py") for name in files),
        "allBytesEqual": not differing and not missing,
        "differing": differing,
        "missing": missing,
        "backendImportsShipped": sorted(backend_imports(repo) - {n[:-3].replace("/", ".") for n in files}) == [],
        "files": files,
    }
    resources = {}
    for app in ("worker", "server"):
        committed = repo / "desktop" / app / "resources"
        for platform in ("linux-unpacked", "win-unpacked"):
            packaged = build / app / platform / "resources" / app
            names = sorted(p.name for p in packaged.iterdir())
            unequal = [n for n in names if (committed / n).read_bytes() != (packaged / n).read_bytes()]
            resources[f"{app}/{platform}"] = {"files": names, "allEqualCommitted": not unequal, "unequal": unequal}
    result["packagedResources"] = resources
    print(json.dumps(result, indent=2))
    ok = result["worker"]["membershipModulePresent"] and result["server"]["backendImportsShipped"]
    ok = ok and all(result[a]["allBytesEqual"] for a in ("worker", "server"))
    return 0 if ok and all(r["allEqualCommitted"] for r in resources.values()) else 1


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
