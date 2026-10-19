"""A short SDK example with a local model and arbitrary-column JSONL data.

PYTHONPATH=runtime/src python runtime/examples/v3/train.py --model-path MODEL --model-id ORG/MODEL --dataset DATA --out RUN
"""

import argparse

from heteroes.sdk import ESConfig, ESTrainer
from keyword_reward import keyword_hit


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-path", required=True)
    parser.add_argument("--model-id", required=True)
    parser.add_argument("--dataset", required=True, help="JSON/JSONL/CSV with question and keyword columns")
    parser.add_argument("--out", required=True)
    parser.add_argument("--device", default="cpu", choices=["cpu", "cuda"])
    parser.add_argument("--workers", default=1, type=int)
    parser.add_argument("--lora", action="store_true")
    opts = parser.parse_args()
    args = ESConfig(
        model_path=opts.model_path,
        model_id=opts.model_id,
        train_dataset=opts.dataset,
        prompt_field="question",
        population=4,
        generations=2,
        batch_size=4,
        max_new_tokens=32,
        weight_space={"kind": "lora", "rank": 4, "alpha": 8, "targetModules": ["q_proj", "v_proj"]}
        if opts.lora
        else {"kind": "full"},
    )
    for summary in ESTrainer(args, reward_func=keyword_hit).train(opts.out, device=opts.device, workers=opts.workers):
        print(summary)


if __name__ == "__main__":
    main()
