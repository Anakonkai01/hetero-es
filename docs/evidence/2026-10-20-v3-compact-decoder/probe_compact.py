"""GPU probe: Recipe v3 texts and time with `hf_generate` and `hf_compact` on the same rows (pinned Qwen2.5-0.5B, FP32).

    HETEROES_GPU_ACCEPTANCE=1 python -I probe_compact.py --gpu --source runtime/src MODEL_DIR ROWS.jsonl OUT.json

Both decoders run the same left-padded prompts in chunks of 16 (the v3 default) with no system prompt and 256 new
tokens; each decoder runs twice, alternating, so that warm-up is not counted for one side only.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--gpu", action="store_true", required=True)
    parser.add_argument("model", type=Path)
    parser.add_argument("rows", type=Path)
    parser.add_argument("out", type=Path)
    parser.add_argument("--count", type=int, default=500)
    parser.add_argument(
        "--source", type=Path, required=True, help="the runtime's src directory (-I ignores PYTHONPATH)"
    )
    args = parser.parse_args()
    sys.path.insert(0, str(args.source.resolve()))
    if os.environ.get("HETEROES_GPU_ACCEPTANCE") != "1":
        parser.error("set HETEROES_GPU_ACCEPTANCE=1")
    import torch

    from heteroes.eval.precision import EvalModel
    from heteroes.model.loading import load_pinned_model
    from heteroes.runtime_info import code_info, environment_info
    from heteroes.study.evaluation import generate_rows

    rows = [json.loads(line) for line in args.rows.read_text().splitlines()[: args.count]]
    loaded = load_pinned_model(args.model, "cuda")
    model = EvalModel(loaded.model, "float32").model
    results, texts = {}, {}
    for decoder in ("hf_generate", "hf_compact", "hf_generate", "hf_compact"):
        torch.cuda.synchronize()
        started = time.perf_counter()
        raw = generate_rows(
            model, loaded.tokenizer, rows, {"systemPrompt": None, "maxNewTokens": 256, "decoder": decoder}, 16
        )
        torch.cuda.synchronize()
        results.setdefault(decoder, []).append(time.perf_counter() - started)
        outputs = [r["output"] for r in raw]
        if decoder in texts and texts[decoder] != outputs:
            raise SystemExit(f"{decoder} is not repeatable across two runs")
        texts[decoder] = outputs
    different = [i for i, (a, b) in enumerate(zip(texts["hf_generate"], texts["hf_compact"], strict=True)) if a != b]
    report = {
        "rows": len(rows),
        "rowsSha256": hashlib.sha256(args.rows.read_bytes()).hexdigest(),
        "seconds": results,
        "speedup": min(results["hf_generate"]) / min(results["hf_compact"]),
        "differentTexts": len(different),
        "differentRows": different[:50],
        "outputsSha256": {
            k: hashlib.sha256(json.dumps(v, ensure_ascii=False).encode()).hexdigest() for k, v in texts.items()
        },
        "environment": environment_info("cuda"),
        "code": code_info(),
    }
    args.out.write_text(json.dumps(report, indent=1) + "\n")
    print(json.dumps({k: report[k] for k in ("rows", "seconds", "speedup", "differentTexts")}))


if __name__ == "__main__":
    main()
