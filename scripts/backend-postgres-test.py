#!/usr/bin/env python3
"""Own one ephemeral PostgreSQL test container, run the entire backend and always remove only that container."""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys
import time

from sqlalchemy.engine import URL

ROOT = Path(__file__).resolve().parents[1]
IMAGE = "postgres:17-alpine"


def docker(*arguments, environment=None):
    result = subprocess.run(
        ["docker", *arguments],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    if result.returncode:
        # No environment or private connection value is included in an error message.
        raise RuntimeError("Owned PostgreSQL Docker operation failed: " + arguments[0])
    return result.stdout.strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out", type=Path, help="Fresh receipt directory (default: .scratch/check-backend-postgres-<id>)"
    )
    args = parser.parse_args()
    identifier = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + secrets.token_hex(3)
    output = (args.out or ROOT / ".scratch" / ("check-backend-postgres-" + identifier)).resolve()
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    name = "heteroes-minicloud-pgtest-" + identifier.lower()
    environment = {
        **os.environ,
        "POSTGRES_PASSWORD": secrets.token_urlsafe(32),
        "POSTGRES_USER": "heteroes_test",
        "POSTGRES_DB": "heteroes_test",
    }
    receipt = {
        "image": IMAGE,
        "container": name,
        "binding": "127.0.0.1",
        "startedAt": identifier,
        "scope": "all backend/tests",
        "cleanedUp": False,
    }
    created = False
    try:
        available = subprocess.run(["docker", "image", "inspect", IMAGE], capture_output=True).returncode == 0
        if not available:
            docker("pull", IMAGE)
        docker(
            "run",
            "--detach",
            "--rm",
            "--name",
            name,
            "--label",
            "com.docker.compose.project=heteroes-minicloud",
            "--publish",
            "127.0.0.1::5432",
            "--env",
            "POSTGRES_PASSWORD",
            "--env",
            "POSTGRES_USER",
            "--env",
            "POSTGRES_DB",
            IMAGE,
            environment=environment,
        )
        created = True
        for _ in range(60):
            ready = subprocess.run(
                ["docker", "exec", name, "pg_isready", "-U", "heteroes_test", "-d", "heteroes_test"],
                capture_output=True,
            )
            if ready.returncode == 0:
                break
            time.sleep(0.5)
        else:
            raise RuntimeError("Owned PostgreSQL did not become ready")
        binding = docker("port", name, "5432/tcp")
        if not binding.startswith("127.0.0.1:") or "\n" in binding:
            raise RuntimeError("Owned PostgreSQL has an unexpected network binding")
        port = int(binding.rsplit(":", 1)[1])
        version = docker(
            "exec", name, "psql", "-U", "heteroes_test", "-d", "heteroes_test", "-At", "-c", "SHOW server_version_num"
        )
        if not 170000 <= int(version) < 180000:
            raise RuntimeError("The matrix requires PostgreSQL 17")
        receipt.update(
            port=port,
            serverVersionNumber=int(version),
            imageDigest=docker("image", "inspect", IMAGE, "--format", "{{index .RepoDigests 0}}"),
        )
        url = URL.create(
            "postgresql+psycopg",
            username="heteroes_test",
            password=environment["POSTGRES_PASSWORD"],
            host="127.0.0.1",
            port=port,
            database="heteroes_test",
        )
        test_environment = {
            **os.environ,
            "CUDA_VISIBLE_DEVICES": "",
            "HETEROES_TEST_DATABASE_URL": url.render_as_string(hide_password=False),
            "HETEROES_TEST_DATABASE_AUDIT_FILE": str(output / "database-targets.json"),
        }
        with (output / "pytest.log").open("w") as log:
            completed = subprocess.run(
                [sys.executable, "-m", "pytest", "-q", "--tb=short", "backend/tests"],
                cwd=ROOT,
                env=test_environment,
                stdout=log,
                stderr=subprocess.STDOUT,
            )
        receipt["pytestExitCode"] = completed.returncode
        log_text = (output / "pytest.log").read_text()
        summary = [
            line
            for line in log_text.splitlines()
            if re.search(r"\d+ (passed|failed|error|skipped)", line) and not line.startswith("E")
        ]
        receipt["pytestSummary"] = summary[-1] if summary else "No pytest result summary"
        print(receipt["pytestSummary"])
        audit = json.loads((output / "database-targets.json").read_text())
        receipt["productStores"] = audit["productStores"]
        receipt["explicitSQLiteContracts"] = len(audit["explicitSQLiteContracts"])
        assert audit["productStores"]["postgresql"] > 0, "The matrix exercised no PostgreSQL product Stores"
        assert all(
            "sqlite" not in dialects or node in audit["explicitSQLiteContracts"]
            for node, dialects in audit["tests"].items()
        ), "An ordinary product test used SQLite during the PostgreSQL matrix"
        print("Product database targets:", json.dumps(receipt["productStores"], sort_keys=True))
        return completed.returncode
    finally:
        if created:
            docker("rm", "--force", name)
            receipt["cleanedUp"] = True
        (output / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
        print("PostgreSQL matrix receipt:", output / "receipt.json")


if __name__ == "__main__":
    raise SystemExit(main())
