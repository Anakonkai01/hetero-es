from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tarfile
base = Path('docs/evidence/2026-10-25-simt-vector')
archive = Path('.scratch/strict-integer-20261025/simt-vector-thao-source-01.tar.gz')
assert not archive.exists()
with tarfile.open(archive, 'w:gz') as bundle:
    bundle.add('.scratch/strict-integer-20261025/simt-vector-01/src', arcname='src', filter=lambda t: None if '__pycache__' in t.name else t)
    bundle.add('runtime/src', arcname='baseline-src', filter=lambda t: None if '__pycache__' in t.name else t)
    for name in ['runtime/tests/eval/test_integer_cuda.py', 'runtime/scripts/benchmark_inference.py', 'runtime/scripts/probe_strict_backend.py']:
        bundle.add(name, arcname=name)
    bundle.add('.scratch/strict-integer-20261025/bench_simt_vector_paired_01.py', arcname='bench-paired-01.py')
assert (base / 'bench-paired-01.py').read_bytes() == Path('.scratch/strict-integer-20261025/bench_simt_vector_paired_01.py').read_bytes()
host='thao_nguyen@100.92.20.58'
stage='/tmp/heteroes-simt-vector-20261025-01'
cfg='/home/pc5070ti/.ssh/config'
ssh=['ssh','-F',cfg,'-o','BatchMode=yes',host]
scp=['scp','-F',cfg,'-o','BatchMode=yes']
python='/home/thao_nguyen/.local/share/heteroes-c4-cpu/runtimes/9a553d2dfae9/python/bin/python3.12'
deps='/tmp/heteroes-integer-decode-plan-20261025-01/testdeps'
subprocess.run(ssh+['mkdir '+shlex.quote(stage)], check=True)
subprocess.run(scp+[str(archive),host+':'+stage+'/source.tar.gz'],check=True)
subprocess.run(ssh+['tar -xzf '+shlex.quote(stage+'/source.tar.gz')+' -C '+shlex.quote(stage)],check=True)
def call(arguments, output, source):
    assert not (base/output).exists()
    env=['env','LD_LIBRARY_PATH=/usr/lib/wsl/drivers/nv_dispi.inf_amd64_feedb8c0271ca811:/usr/lib/wsl/lib','HETEROES_GPU_ACCEPTANCE=1','PYTHONPATH='+source+':'+deps]
    result=subprocess.run(ssh+['cd '+shlex.quote(stage)+' && '+shlex.join([*env,python,*arguments])+' > '+shlex.quote(output)+' 2>&1'] if output.endswith('.log') else ssh+['cd '+shlex.quote(stage)+' && '+shlex.join([*env,python,*arguments])])
    subprocess.run(scp+[host+':'+stage+'/'+output,str(base/output)],check=True)
    if result.returncode:
        sys.exit(result.returncode)
call(['-m','pytest','runtime/tests/eval/test_integer_cuda.py','-q','-k','simt_exact'],'operator-thao-01.log','src')
models={
 'smol':'/home/thao_nguyen/.cache/heteroes-strict-models-20261025/SmolLM2-360M-Instruct/a10cc1512eabd3dde888204e902eca88bddb4951',
 'tiny':'/home/thao_nguyen/.cache/heteroes-strict-models-20261025/TinyLlama-1.1B-Chat-v1.0/fe8a4ea1ffedaf415f4da2f062534de366a451e6',
 'qwen':'/home/thao_nguyen/.local/share/heteroes-c4-cpu/models/7ae557604adf67be50417f59c2c2f167def9a775',
}
for model,path in models.items():
    out=f'paired-{model}-thao-01.json'
    call(['bench-paired-01.py','--gpu','--model-path',path,'--candidate-source','src/heteroes/eval/integer_cuda.py','--out',out],out,'baseline-src')
