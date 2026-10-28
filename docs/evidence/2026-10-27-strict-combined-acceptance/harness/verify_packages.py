"""Verify all runtime Python bytes in the actual Linux Worker archive and Server-embedded SDK wheel."""
import hashlib,io,json,subprocess,tarfile,zipfile
from pathlib import Path
root=Path('.scratch/codex-20261027-linux-check-03');out=Path('docs/evidence/2026-10-27-strict-combined-acceptance/raw')
commit='0eb86cb948878fe430049882b80b3a5ad74730ba'
archive=subprocess.check_output(['git','archive',commit,'runtime/src'])
with tarfile.open(fileobj=io.BytesIO(archive)) as t:
 expected={m.name.removeprefix('runtime/src/'):t.extractfile(m).read() for m in t.getmembers() if m.isfile() and m.name.endswith('.py')}
worker=root/'worker/linux-unpacked/resources/worker/runtime.tar.gz'
server=root/'server/linux-unpacked/resources/server/runtime.tar.gz'
with tarfile.open(worker) as t:actual={m.name.removeprefix('src/'):t.extractfile(m).read() for m in t.getmembers() if m.isfile() and m.name.startswith('src/') and m.name.endswith('.py')}
assert actual==expected
with tarfile.open(server) as t:
 names=[n for n in t.getnames() if n.startswith('web/notebooks/') and n.endswith('.whl')];assert len(names)==1
 wheel=t.extractfile(names[0]).read()
with zipfile.ZipFile(io.BytesIO(wheel)) as z:actual={n:z.read(n) for n in z.namelist() if n.startswith('heteroes/') and n.endswith('.py')}
assert actual==expected
receipt=json.loads((root/'receipt.json').read_text());assert receipt['linuxOnly'] and not receipt['published'] and all(a['sharedModulesImport'] for a in receipt['apps'])
result={'status':'ok','runtimeCommit':commit,'packageReceiptCommit':receipt['sourceCommit'],'runtimePythonFiles':len(expected),'packagedWorkerMatchesCommit':True,'packagedServerSdkMatchesCommit':True,'workerArchiveSha256':hashlib.sha256(worker.read_bytes()).hexdigest(),'serverArchiveSha256':hashlib.sha256(server.read_bytes()).hexdigest(),'embeddedSdkSha256':hashlib.sha256(wheel).hexdigest(),'limits':'Linux source build/import and byte verification only. No installer, managed execution or GPU execution of installed packages.'}
with (out/'package-source-01.json').open('x') as f:json.dump(result,f,indent=2);f.write('\n')
print(json.dumps(result))
