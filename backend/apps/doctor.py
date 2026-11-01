"Read-only preflight for a Local Lab Server. It changes no lab file (SQLite may create its\n-shm coordination file when it opens the WAL database); exit status 1 if any check FAILs.\n\n    python -m backend.doctor --private ~/.config/heteroes-m2\n"

import argparse
from pathlib import Path
from ..services.doctor import run_checks, FAIL


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--private", type=Path, required=True, help="private lab directory (contains config.json)")
    results = run_checks(parser.parse_args(argv).private)
    for level, name, message in results:
        print(f"{level:4}  {name:14} {message}")
    failed = sum(level == FAIL for level, _, _ in results)
    print("\n" + (f"{failed} check(s) FAILED." if failed else "No failures."))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
