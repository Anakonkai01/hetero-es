"""Print the numbers of README.md from the reports of this folder: python3 summarize.py"""

import gzip
import json
from pathlib import Path
import statistics

HERE = Path(__file__).parent
for name in ("plain", "fault", "soak"):
    r = json.loads((HERE / name / "report.json").read_text())
    audits = r["auditPairs"]
    print(
        f"{name}: generations {r['generations']}, failures {r['failures']}, results {r['resultsByWorker']}, "
        f"expired {r.get('expiredByWorker')}, audits {len(audits)} matched {sum(m == 1 for *_, m in audits)}, "
        f"distinct children {len(set(r['children']))}, fault {(r.get('fault') or {}).get('generation')}"
    )
plain, fault = (json.loads((HERE / n / "report.json").read_text()) for n in ("plain", "fault"))
print(
    "plain == fault children and records:",
    (plain["children"], plain["recordHashes"]) == (fault["children"], fault["recordHashes"]),
)
soak = json.loads(gzip.decompress((HERE / "soak" / "summaries.json.gz").read_bytes()))
total = [row["total_seconds"] for row in soak]
print("soak bookkeeping thirds:", json.loads((HERE / "soak" / "report.json").read_text())["bookkeeping"])
print(
    f"soak generation seconds: median {statistics.median(total):.3f}, max {max(total):.3f}; updates that changed weights {sum(1 for row in soak if row['changed'])}"
)
