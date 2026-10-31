import dataclasses
import hashlib
import json
from pathlib import Path
import platform
import re
import torch
import transformers
from transformers import AutoModelForCausalLM, AutoTokenizer
from heteroes.eval.workload import EXAMPLES, SYSTEM_PROMPT, MAX_NEW_TOKENS, workload_hash

root=Path('/home/thao_nguyen/.cache/heteroes-codex-frozen-perf-20261025-01/models/qwen')
model=AutoModelForCausalLM.from_pretrained(root,dtype=torch.float16).to('cuda')
tokenizer=AutoTokenizer.from_pretrained(root)
records=[]
for example in EXAMPLES:
 inputs=tokenizer.apply_chat_template([{'role':'system','content':SYSTEM_PROMPT},{'role':'user','content':example.question}],return_tensors='pt',return_dict=True,add_generation_prompt=True,tokenize=True)
 inputs={k:v.to('cuda') for k,v in inputs.items()}
 with torch.inference_mode():
  output=model.generate(**inputs,max_new_tokens=MAX_NEW_TOKENS,do_sample=False)
 text=tokenizer.batch_decode(output[:,inputs['input_ids'].shape[1]:],skip_special_tokens=True)[0].strip()
 numbers=re.findall(r'-?\d+',text.replace(',',''))
 prediction=int(numbers[-1]) if numbers else None
 records.append({'question':example.question,'expected':example.answer,'output_text':text,'prediction':prediction,'reward':float(prediction==example.answer)})
result={'format':'heteroes-qwen-fp16-reference-v1','capturedAt':'2026-11-01','scope':'HF FP16 greedy arith16, RTX 3060 SM86; this is not strict cross-GPU identity or a learning result.','gpu':torch.cuda.get_device_name(),'computeCapability':list(torch.cuda.get_device_capability()),'python':platform.python_version(),'torch':torch.__version__,'transformers':transformers.__version__,'workloadHash':workload_hash(),'modelFileSha256':hashlib.sha256((root/'model.safetensors').read_bytes()).hexdigest(),'base_evaluation':{'mean_reward':sum(r['reward'] for r in records)/len(records),'records':records}}
print(json.dumps(result,indent=2))
