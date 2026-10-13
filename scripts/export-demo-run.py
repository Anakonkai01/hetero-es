#!/usr/bin/env python3
"""Export one finished run of the real lab as the timeline JSON the website replays on its home page.

    export-demo-run.py --db ~/.config/heteroes-m2/state/product.sqlite --run <experiment id> --out frontend/static/demo/run.json

Reads the product database READ-ONLY. The file holds only what the Live screen draws: GPU names, candidate/attempt times,
generation times and rewards. No user names, accounts, paths, hashes or addresses.
"""
import argparse
import json
from pathlib import Path
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.timeline import build_timeline  # noqa: E402

KEEP_MARKS = {'worker_start', 'executor_ready', 'replay', 'worker_unavailable', 'recovered'}


def export_timeline(body, snapshot):
    """The public, anonymous timeline of a finished run."""
    timeline = build_timeline(body, snapshot)
    end = timeline['experiment']['completedMs'] or timeline['nowMs']
    timeline['nowMs'] = end
    timeline['experiment'] = {**timeline['experiment'], 'id': 'demo', 'name': 'Demo run'}
    timeline['marks'] = [{key: value for key, value in mark.items() if key != 'detail'} for mark in timeline['marks'] if mark['type'] in KEEP_MARKS]
    for job in timeline['jobs']:
        job.pop('seed', None)
        job['candidateId'] = job['candidateId'].rsplit('.', 1)[-1] if job['candidateId'] else None
        job['attemptId'] = None
    for generation in timeline['generations']:
        generation['id'] = f"g{generation['index']}"
    return timeline


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--db', type=Path, required=True)
    parser.add_argument('--run', required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    db = sqlite3.connect(f'file:{args.db}?mode=ro', uri=True, timeout=10)
    row = db.execute('SELECT body, snapshot FROM experiments WHERE id=?', (args.run,)).fetchone()
    if not row or not row[1]:
        raise SystemExit('Unknown run or no snapshot')
    body, snapshot = json.loads(row[0]), json.loads(row[1])
    if body.get('status') != 'COMPLETED':
        raise SystemExit('Only a COMPLETED run can be exported')
    timeline = export_timeline(body, snapshot)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(timeline, separators=(',', ':'), allow_nan=False) + '\n')
    print(f'wrote {args.out} ({args.out.stat().st_size} bytes): {len(timeline["jobs"])} jobs, {len(timeline["workers"])} GPUs, {len(timeline["generations"])} generations')


if __name__ == '__main__':
    main()
