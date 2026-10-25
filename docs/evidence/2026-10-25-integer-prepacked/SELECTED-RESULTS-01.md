# Selected source1848d57c

Activation radix bytes are packed once per call and reused across output tiles. Live FP16 weights, integer
arithmetic and final rounding are unchanged. Narrow-width padding is admitted before allocation.

|5070Ti total output token/s|B1|B8|B32|B32 gain versus97f62431|
|---|---:|---:|---:|---:|
|SmolLM2-360M|258.7|1335.5|3386.2|18.3%|
|TinyLlama-1.1B|182.2|744.8|1678.5|21.9%|
|Qwen2.5-0.5B|265.1|1291.4|3192.9|13.6%|

396 tests pass on each of four GPUs: local/Nhut5070Ti, Quang3060WSL2 and Thao3060native Windows. Check-all ALL PASS;
6/6 scratch mutants killed. Worker runtime and embedded Server SDK match all nine selected runtime files.
Four pinned fixture layouts, both precisions and all states match between Linux5070Ti and native Windows3060;
all available compiler audits have zero violations. See native-windows-comparison-01.json.
Three trained models' parent/canonical7001±/restored weights, prefill hashes, token streams, text and rewards match
97f62431 for the old FP32 tree and both integer precisions; exact restored parent. See selected-trained-comparison-01.json.

## What this does NOT show

No managed/default activation, general quality theorem, native installer acceptance or completion of M0–M6.
B32 remains about22–24% of measured vLLM default. Current-source trained3060 checks and new profiling are separate
in-progress receipts. Failed/slower integer conversion variants and segmented grouping remain unselected.
No push/merge/deploy, device-state change or learning.
