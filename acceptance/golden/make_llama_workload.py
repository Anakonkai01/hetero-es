#!/usr/bin/env python3
"""Build workload-chat-llama32.json: the same 64 GSM8K chat rows as workload-chat-01.json (Qwen), in Llama 3.2's chat
template, for the strict parity probe of unsloth/Llama-3.2-1B-Instruct (revision 5a8abab4…).

The system and user text are taken from the Qwen rows, so both workloads ask the same questions. Llama 3.2's template
writes "Today Date" into the system turn; it is pinned (`date_string`) so the token ids never depend on the day the file
is built. The token ids are stored, so the probe never runs the template itself.

    python3 acceptance/golden/make_llama_workload.py <llama32 model dir> > acceptance/golden/workload-chat-llama32.json
"""

import hashlib
import json
from pathlib import Path
import re
import sys

from transformers import AutoTokenizer

HERE = Path(__file__).resolve().parent
DATE = "26 Nov 2026"
source = HERE / "workload-chat-01.json"
qwen = json.loads(source.read_text())
tokenizer = AutoTokenizer.from_pretrained(sys.argv[1])
rows = []
for row in qwen["models"]["qwen"]["rows"]:
    turns = dict(re.findall(r"<\|im_start\|>(system|user)\n(.*?)<\|im_end\|>", row["text"], flags=re.S))
    messages = [{"role": "system", "content": turns["system"]}, {"role": "user", "content": turns["user"]}]
    text = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True, date_string=DATE)
    ids = tokenizer(text, add_special_tokens=False)["input_ids"]
    rows.append({**{k: row[k] for k in ("id", "group", "answer", "scorer")}, "text": text, "tokenIds": ids})
print(
    json.dumps(
        {
            "gsm8kSliceSha256": qwen["gsm8kSliceSha256"],
            "sourceWorkloadSha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            "totalRows": len(rows),
            "scoredRows": len(rows),
            "promptFormat": f"Llama 3.2 chat template (date_string {DATE!r}), system plus user; generation prompt",
            "models": {"llama32": {"rows": rows}},
        },
        indent=1,
        ensure_ascii=False,
    )
)
