import hashlib,json,os,selectors,secrets,subprocess,sys,tarfile,time
from pathlib import Path
from urllib.error import HTTPError,URLError
from urllib.request import Request,build_opener,ProxyHandler
root=Path(__file__).resolve().parent;out=root
work=out/'private-server-windows';assert not work.exists();work.mkdir()
profile=json.loads((root/'profile.json').read_text());item=profile['platforms']['windows']['python']
interpreter_archive=out/'python-inputs'/item['name'];assert hashlib.sha256(interpreter_archive.read_bytes()).hexdigest()==item['sha256']
with tarfile.open(interpreter_archive) as archive:archive.extractall(work/'interpreter',filter='data')
python=work/'interpreter/python/python.exe'
source=work/'source'
package=root/'runtime.tar.gz';assert hashlib.sha256(package.read_bytes()).hexdigest()==profile['runtimeSha256']
with tarfile.open(package) as archive:
 names=archive.getnames();assert 'backend/db/postgres_schema.sql' in names and not any('/tests/' in name for name in names)
 archive.extractall(source,filter='data')
env={**os.environ,'CUDA_VISIBLE_DEVICES':''}
for name in tuple(env):
 if name.startswith('HETEROES_'):env.pop(name)
with (out/'private-server-install.log').open('w') as log:
 subprocess.run([str(python),'-I','-m','pip','--isolated','install','--no-index','--no-cache-dir','--find-links',str(out/'server-wheelhouse/windows'),'--require-hashes','-r',str(root/'requirements-windows.txt')],env=env,stdout=log,stderr=subprocess.STDOUT,check=True)
code='''
import importlib.metadata,importlib.util,json,socket,sys
from pathlib import Path
settings=json.load(sys.stdin)
sys.path.insert(0,settings['source'])
optional=('torch','psycopg','boto3','jwt','cryptography','prometheus_client')
assert all(importlib.util.find_spec(name) is None for name in optional)
from backend.apps.factory import create_app
from backend.services.devices import AgentRuntime
from backend.storage.local_backend import LocalBackend
import uvicorn
listener=socket.socket();listener.bind(('127.0.0.1',0))
origin='http://127.0.0.1:'+str(listener.getsockname()[1])
state=Path(settings['state'])
app=create_app(state/'product.sqlite',{'admin':settings['password']},AgentRuntime(LocalBackend(state/'objects',state/'signing.key',origin)),dispatch=False,web_directory=Path(settings['source'])/'web')
assert not any(name in sys.modules for name in optional)
print(json.dumps({'origin':origin,'python':sys.version.split()[0],'prefix':sys.prefix,'sqlalchemy':importlib.metadata.version('SQLAlchemy'),'greenlet':importlib.metadata.version('greenlet'),'optionalCloudAndGPUAbsent':True}),flush=True)
uvicorn.Server(uvicorn.Config(app,access_log=False,log_level='warning')).run(sockets=[listener])
'''
password=secrets.token_urlsafe(32);token=None
process=subprocess.Popen([str(python),'-I','-c',code],cwd=work,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,env=env)
process.stdin.write(json.dumps({'source':str(source),'state':str(work/'private-state'),'password':password}));process.stdin.close();process.stdin=None
requests=[];metadata={};passed=False
try:
 import queue,threading
 announced=queue.Queue()
 threading.Thread(target=lambda:announced.put(process.stdout.readline()),daemon=True).start()
 metadata=json.loads(announced.get(timeout=20));origin=metadata.pop('origin')
 assert metadata['python']==profile['pythonVersion'] and str(work) in metadata['prefix']
 assert metadata['sqlalchemy']=='2.0.55' and metadata['greenlet']=='3.4.0'
 client=build_opener(ProxyHandler({}))
 def request(path,body=None,headers=None):
  data=json.dumps(body).encode() if body is not None else None
  h={'Content-Type':'application/json',**(headers or {})}
  with client.open(Request(origin+path,data=data,headers=h),timeout=5) as response:
   payload=response.read();assert response.status==200
   requests.append({'path':path,'status':response.status})
   return payload
 deadline=time.monotonic()+15
 while True:
  try:
   assert json.loads(request('/healthz'))['ok'];break
  except URLError:
   assert time.monotonic()<deadline;time.sleep(.05)
 assert json.loads(request('/readyz'))['ready']
 assert json.loads(request('/api/v1/health'))['agentMode']
 session=json.loads(request('/api/v1/auth/login',{'username':'admin','password':password}));token=session['accessToken']
 assert json.loads(request('/api/v1/auth/session',headers={'Authorization':'Bearer '+token}))['user']['username']=='admin'
 assert b'heteroes_service_up' in request('/metrics')
 passed=True
finally:
 process.terminate()
 stdout,stderr=process.communicate(timeout=20)
 forbidden=[password]+([token] if token else [])
 leaked=any(value in stdout+stderr for value in forbidden)
 for value in forbidden:stdout=stdout.replace(value,'<redacted>');stderr=stderr.replace(value,'<redacted>')
 (out/'private-server-stdout.log').write_text(stdout);(out/'private-server-stderr.log').write_text(stderr)
 assert not leaked,'Private server emitted a credential'
assert passed and len(requests)==6
receipt={'platform':'windows','profileSha256':hashlib.sha256((root/'profile.json').read_bytes()).hexdigest(),'runtimeSha256':profile['runtimeSha256'],'pythonArchiveSha256':item['sha256'],'metadata':metadata,'requests':requests,'installedPinnedCPUWheels':24,'privateInterpreterHttpPassed':True,'credentialLeak':False,'cleanedUpProcess':process.poll() is not None,'testStatePreservedLocallyOnly':True}
(out/'private-server-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
print('PASS actual private Python installation and6 authenticated/storage HTTP checks; optional cloud/GPU packages absent')
