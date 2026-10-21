"""The GSM8K demo's fixed choices: members of the live lab, the predeclared tier specs and where their receipts live."""

import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
EVIDENCE = REPO / "docs" / "evidence" / "2026-10-22-gsm8k-demo"
RECEIPTS = REPO / ".scratch" / "gsm8k-demo"  # lab-offer.json per tier: asset ids and the experiment id (no secrets)

COORDINATOR_DEVICE = "dbe5254b78de4c038550b8b90df13899"  # 5070ti-nhan
NAMES = {
    "cli-71b757062fd9": "5070ti-nhan",
    "cli-73b87e369ddc": "quang-3060",
    "desktop-d9017660e75f": "3060-thao",
    "cli-d90d1da024e9": "1660s",
    "cli-aa99b4d4ca58": "5070ti-nhut",  # added 2026-10-21 night (PREDECLARATION-tier2b.md, amendment)
}
WORKERS = list(NAMES)
OPTIONAL = {"cli-d90d1da024e9"}  # the 1660S has a PCI fault and may switch off


def spec(tier):
    return json.loads((EVIDENCE / f"{tier}.json").read_text())


def launch(lab, tier, workers=None):
    """Offer and submit a tier once; calling it again returns the same experiment (the receipt is idempotent)."""
    root = RECEIPTS / tier
    root.mkdir(parents=True, exist_ok=True)
    return lab.offer(spec(tier), COORDINATOR_DEVICE, workers or WORKERS, root)


def run_id(tier):
    receipt = RECEIPTS / tier / "lab-offer.json"
    return json.loads(receipt.read_text()).get("experimentId") if receipt.exists() else None
