# G6: the same as `../2026-10-07-g6-local-scaling/`, with the FP32 forward pass and 16 prompts per call

`--eval-dtype float32 --chunk 16` (see `../2026-10-07-g6-cross-gpu/README.md` and numerical contract section 15). The table and the reading are in
`../2026-10-07-g6-local-scaling/README.md`; `summary-n24.json` holds the numbers. Every run (one, two, three processes) ended with the same rewards and the same weights hashes.
Two repeats per condition, 4 generations of 24 candidates each.
