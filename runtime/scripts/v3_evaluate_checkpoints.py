"""
Score checkpoints of a local Recipe v3 run (`heteroes run` / `run_local`) on one split of its dataset.

    python v3_evaluate_checkpoints.py RUN_DIR --model-path MODEL --generations -1,9,29 --split validation \
        --out report.json [--device cuda] [--scorer-path reward.py --scorer-function name] \
        [--rows other.jsonl --rows-scorer scorer.json]

The coordinator keeps only its latest weights; any checkpoint is rebuilt here from the base model by replaying the
recorded updates, and each rebuilt checkpoint must hash to the child the ledger recorded (generation -1 is the base
model). Evaluation is the run's: greedy decoding, its prompt, token budget, precision and chunk, scored with its plan's
scorer (a python scorer needs `--scorer-path`, the file whose SHA-256 the plan pins).
`--rows` scores the checkpoints on OTHER rows (a JSONL file of rows with the run's prompt field), for example to look for
forgetting on another task, with the declarative scorer spec in the `--rows-scorer` JSON file instead of the plan's.
GPU use in this repository needs the owner's authorization and HETEROES_GPU_ACCEPTANCE=1.
"""

from heteroes.v3.evaluation import evaluate, main


if __name__ == "__main__":
    main()
