#!/usr/bin/env python3
"""Restore a verified PostgreSQL17 metadata archive into an empty, held target; the connection URL stays in an environment variable."""

import argparse
import json
import os
from pathlib import Path
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, required=True, help="Verified custom-format pg_dump archive")
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument(
        "--target-env",
        default="HETEROES_DATABASE_URL",
        help="Environment variable containing the fresh target database URL",
    )
    args = parser.parse_args()
    os.environ["CUDA_VISIBLE_DEVICES"] = ""
    try:
        target = os.environ.get(args.target_env)
        if not target:
            raise ValueError("Missing target database environment variable")
        if args.manifest.stat().st_size > 16384:
            raise ValueError("Invalid metadata manifest")
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        from backend.db.engine import Database
        from backend.db.postgres_backup import restore_postgres

        manifest = json.loads(args.manifest.read_text())
        with Database(target) as database:
            receipt = restore_postgres(args.database, manifest, database)
        print(json.dumps(receipt, indent=2))
        return 0
    except Exception as error:
        print(json.dumps({"error": type(error).__name__}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
