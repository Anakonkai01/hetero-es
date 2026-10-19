"""The pinned model, the workload names and the decode engines are written once, in runtime/src/heteroes/catalog.py."""

from pathlib import Path
import re

from heteroes import catalog

REPO = Path(__file__).resolve().parents[2]
# Production sources only: experiment scripts and evidence record what past runs used and stay as they are.
PRODUCTION = [*(REPO / "runtime/src/heteroes").rglob("*.py"), *(REPO / "backend").glob("*.py")]


def copies(pattern):
    return sorted(
        path.relative_to(REPO).as_posix()
        for path in PRODUCTION
        if path.name != "catalog.py" and re.search(pattern, path.read_text(encoding="utf-8"))
    )


def quoted_sequence(values):
    # the values written out in order as string literals, whatever the brackets and spacing: a copied tuple, list or set
    return r"\s*,\s*".join(f"[\"']{re.escape(value)}[\"']" for value in values)


def test_the_pinned_checkpoint_is_written_only_in_the_catalog():
    assert copies(re.escape(catalog.PINNED_REVISION)) == []
    assert copies(f"[\"']{re.escape(catalog.PINNED_MODEL_ID)}[\"']") == []


def test_the_workload_names_and_decode_engines_are_not_copied_as_a_list():
    assert copies(quoted_sequence(catalog.WORKLOAD_NAMES)) == []
    assert copies(quoted_sequence(catalog.DECODE_ENGINES)) == []


def test_the_scan_finds_a_copy_when_there_is_one(tmp_path):
    # premise: the patterns match the forms the copies had before 2026-10-19
    before = """WORKLOADS = ("arith16", "cot_l3_q32", "cot_l3_q64", "cot_l1_q128")
"workloads": ["arith16", "cot_l3_q32", "cot_l3_q64", "cot_l1_q128"],
"decodeEngine": {"hf_generate", "hf_compact"},
MODEL = "Qwen/Qwen2.5-0.5B-Instruct"
REVISION = "7ae557604adf67be50417f59c2c2f167def9a775"
"""
    assert len(re.findall(quoted_sequence(catalog.WORKLOAD_NAMES), before)) == 2
    assert re.search(quoted_sequence(catalog.DECODE_ENGINES), before)
    assert re.search(f"[\"']{re.escape(catalog.PINNED_MODEL_ID)}[\"']", before)
    assert re.search(re.escape(catalog.PINNED_REVISION), before)
