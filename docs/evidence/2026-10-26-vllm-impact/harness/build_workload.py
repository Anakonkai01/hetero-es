"""Freeze one CPU-created prompt/answer/token corpus for both GPUs."""
from pathlib import Path
import hashlib
import json

from transformers import AutoTokenizer
from probe_strict_backend import PROMPTS, EXPECTED, generated_prompts

root = Path('docs/evidence/2026-10-26-vllm-impact')
slice_path = root/'gsm8k-slice-01.json'
gsm = json.loads(slice_path.read_text())
rows = [{'id':f'historical-{i:03}','group':'historical','text':text,
         'answer':None if EXPECTED[i] is None else str(EXPECTED[i]),'scorer':'last-integer'}
        for i,text in enumerate(PROMPTS)]
for i,text in enumerate(generated_prompts(200)):
    a,b,c = 3+(i*7)%41,2+(i*11)%23,2+(i*5)%9
    rows.append({'id':f'historical-{i+8:03}','group':'historical','text':text,
                 'answer':str(a+b-(a+b)//c),'scorer':'last-integer'})
for row in gsm['rows']:
    rows.append({'id':f'gsm8k-test-{row["index"]:03}','group':'gsm8k-first64',
                 'text':row['question']+"\nSolve step by step. End with a line 'Answer: <number>'.",
                 'answer':row['answer'],'scorer':'answer-line-last-number'})
report = {'gsm8kSliceSha256':hashlib.sha256(slice_path.read_bytes()).hexdigest(),
          'scoredRows':269,'totalRows':272,'models':{}}
for model in ('qwen','smol','tiny'):
    tokenizer = AutoTokenizer.from_pretrained('/home/pc5070ti/projects/heteroes/.scratch/strict-integer-20261025/models/'+model,
                                              local_files_only=True,trust_remote_code=False)
    actual = [{**row,'tokenIds':tokenizer(row['text'])['input_ids']} for row in rows]
    assert max(len(r['tokenIds']) for r in actual)+256 <= 1024
    report['models'][model] = {'rows':actual}
    print(model,len(actual),'max prompt tokens',max(len(r['tokenIds']) for r in actual))
with (root/'workload-01.json').open('x') as f:
    json.dump(report,f,indent=2)
    f.write('\n')
