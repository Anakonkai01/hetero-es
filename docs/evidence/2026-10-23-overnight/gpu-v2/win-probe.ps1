$ErrorActionPreference='Stop'
$env:HETEROES_GPU_ACCEPTANCE='1'
$py='F:\HeteroES-Worker-data\runtimes\f731d5a12cb4\python\python.exe'
& $py -I 'F:\HeteroES-Worker-data\c15-probe\probe_v2_cuda.py' 'F:\HeteroES-Worker-data\c15-probe\probe-src' --gpu 2>&1 | Select-Object -Last 5
