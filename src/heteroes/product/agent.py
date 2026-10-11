"""Outbound device agent. Typed commands, boot-scoped opt-in, owned processes only."""
import argparse
import base64
import hashlib
import getpass
import json
import os
from pathlib import Path
import re
import secrets
import signal
import sqlite3
import sys
import time
import threading
import urllib.error
import urllib.request
import uuid
from .files import events,read_json,write_json
from .gateway import Manager,TERMINAL,ROOT,validate
from .remote import alive,identity,worker_environment,handle as remote_handle
from .platform_process import acquire_instance_lock, ProcessIdentityUnknown, spawn_options


def request(url, path, token, body, method=None):
    req=urllib.request.Request(url.rstrip('/')+path,data=None if body is None else json.dumps(body,allow_nan=False).encode(),method=method,
        headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'})
    # Never expose exception URLs, token-bearing bodies or server tracebacks.
    with urllib.request.urlopen(req,timeout=15) as response:
        return json.load(response)


def owned_state(record,intent=False):
    if record is None:return None if intent else False
    if record.get('birth') is None or type(record.get('pid')) is not int:return None
    try:return alive(record)
    except ProcessIdentityUnknown:return None


def bounded_snapshot(snapshot,max_bytes=1_250_000):
    """Bound heartbeat detail while preserving final state and global counters.

    Complete events are spooled separately before this projection is reduced.
    Full candidate history remains in the canonical ledger/recovery points.
    """
    generations=snapshot['generations']
    snapshot['completedGenerationCount']=sum(g['status']=='COMPLETED' for g in generations)
    snapshot['latestGeneration']=generations[-1] if generations else None
    def size():return len(json.dumps(snapshot,allow_nan=False).encode())
    for key in ('events','attempts','candidates','generations'):
        while snapshot[key] and size()>max_bytes:
            snapshot[key]=snapshot[key][max(1,len(snapshot[key])//2):]
            snapshot['monitoringPartial']=True
    while snapshot.get('artifactContents') and size()>max_bytes:
        largest=max(snapshot['artifactContents'],key=lambda k:len(snapshot['artifactContents'][k]['base64']))
        del snapshot['artifactContents'][largest];snapshot['monitoringPartial']=True
    if size()>max_bytes:raise ValueError('Runtime state exceeds the monitoring budget')
    return snapshot


class AgentManager(Manager):
    def __init__(self,agent):
        self.agent=agent
        cfg={**agent.config,'python':sys.executable,'workerUrl':agent.config['computeUrl'],'stateDirectory':str(agent.root/'runs'),'workers':[]}
        super().__init__(cfg,secrets.token_urlsafe(32))
        self._launch=self.spawn

    def spawn(self,root):
        import subprocess
        env=worker_environment(str(ROOT/'src'),self.token)
        with open(root/'coordinator.log','ab') as output:
            process=subprocess.Popen([sys.executable,'-m','heteroes.product.runner',str(root)],env=env,cwd=ROOT,stdout=output,stderr=output,**spawn_options())
        self.processes[root.name]=process
        write_json(root/'process.json',{'pid':process.pid,'birth':identity(process.pid)})

    def cancel(self,run_id):
        root=self.directory(run_id)
        if (root/'config.json').exists():(root/'cancel.flag').touch(mode=0o600)

    def launch(self,root):
        if self.agent.enabled:
            intent=read_json(root/'launch-intent.json')
            if intent and (intent.get('process') is None or owned_state(intent['process']) is not False):
                raise RuntimeError('Coordinator launch ownership is unknown')
            (root/'dispatch-held.flag').unlink(missing_ok=True)
            write_json(root/'launch-intent.json',{'process':None})
            self._launch(root)
            write_json(root/'launch-intent.json',{'process':read_json(root/'process.json')})

    def remote(self,worker,body):
        # Current ownership stays on this coordinator. The CPU server only relays
        # fixed worker lifecycle commands; it never evaluates a candidate.
        action=body['action'];run=body.get('runId')
        if run:
            run_id,recovery=run.rsplit('-r',1);recovery=int(recovery)
        else:
            pending=[r for r in self.root.iterdir() if r.is_dir() and self.state(r).get('status') not in TERMINAL]
            if len(pending)!=1:raise RuntimeError('No unique active assignment')
            run_id=pending[0].name;recovery=self.state(pending[0]).get('recoveryCount',0)
        ar=read_json(self.directory(run_id)/'assignment.json')
        result=self.agent.call('/api/v1/device/worker-command',{'assignmentId':ar['assignmentId'],'epoch':ar['epoch'],
            'workerId':worker['id'],'action':action,'recoveryIndex':recovery})
        if action!='probe' and result.get('alive') is None:raise ConnectionError('Worker ownership is unknown')
        return result

    def start_worker(self,root,worker,recovery):
        return self.remote(worker,{'action':'start','runId':root.name+f'-r{recovery}'})

    def accept(self,command):
        cfg=command['config']
        self.workers={wid:{'id':wid} for wid in cfg['workerIds']}
        validate(cfg,self.workers)
        self.submit(cfg)
        root=self.directory(cfg['runId'])
        write_json(root/'assignment.json',command)
        write_json(root/'device-grants.json',command['computeGrants'])
        write_json(root/'backup-policy.json',command.get('effectiveBackupPolicy',cfg.get('backupPolicy',{'interval':1,'retain':3})))
        # Operational settings are local/private, outside canonical Recipe v1.
        local=read_json(root/'config.json')
        local.update(backupPolicy=cfg.get('backupPolicy',{'interval':1,'retain':3}),deviceCredentials=True)
        write_json(root/'config.json',local)

    def tick(self,root):
        # Reload only our locally accepted assignment, including after agent restart.
        ar=read_json(root/'assignment.json')
        if not ar:return
        self.workers={w:{'id':w} for w in ar['config']['workerIds']}
        # Dead-process recovery must wait for this boot's owner opt-in. A living
        # child can still be adopted/observed and reach normal shutdown while OFF.
        if not self.agent.enabled and not alive(read_json(root/'process.json')) and read_json(root/'runner.json',{}).get('status') not in TERMINAL:
            return
        if owned_state(read_json(root/'process.json'), (root/'launch-intent.json').exists()) is None:
            self.save(root,status='RECOVERING',failureReason='Coordinator process identity is unknown')
            return
        super().tick(root)


class Agent:
    def __init__(self,path,lock=False,config_override=None):
        self.path=Path(path);self.config={**read_json(path),**(config_override or {})}
        self.root=Path(self.config['stateDirectory']);self.root.mkdir(parents=True,exist_ok=True,mode=0o700)
        self.instance_lock=None
        if lock:
            self.instance_lock=acquire_instance_lock(self.root/'agent.lock')
        self.desktop_lock=threading.RLock()
        self.boot_id=uuid.uuid4().hex;self.enabled=False;self.stopping=False;self.shutdown_requested=False
        write_json(self.root/'boot.json',{'bootId':self.boot_id,'enabled':False})
        self.manager=AgentManager(self)
        self.db_path=self.root/'outbox.sqlite'
        with self.db() as db:
            db.executescript('''CREATE TABLE IF NOT EXISTS processed(id TEXT PRIMARY KEY);
                CREATE TABLE IF NOT EXISTS released(assignment_id TEXT PRIMARY KEY);
                CREATE TABLE IF NOT EXISTS event_outbox(id TEXT PRIMARY KEY,assignment_id TEXT NOT NULL,epoch INTEGER NOT NULL,body TEXT NOT NULL,ack INTEGER NOT NULL DEFAULT 0);
                CREATE TABLE IF NOT EXISTS sequence(assignment_id TEXT PRIMARY KEY,value INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS outbox(assignment_id TEXT PRIMARY KEY,sequence INTEGER NOT NULL,body TEXT NOT NULL);''')
        with self.db() as db:
            if 'ack' not in {r[1] for r in db.execute('PRAGMA table_info(event_outbox)')}:db.execute('ALTER TABLE event_outbox ADD COLUMN ack INTEGER NOT NULL DEFAULT 0')
        os.chmod(self.db_path,0o600)
        # One agent owns this state directory. Kernel lock is released on a crash.

    def db(self):
        return sqlite3.connect(self.db_path)

    def call(self,path,body,method=None):
        return request(self.config['serverUrl'],path,self.config['deviceToken'],body,method=method)

    def worker_directory(self,command):
        run_id=command.get('runId')
        if not re.fullmatch('[a-f0-9]{32}',command.get('assignmentId','')) or type(command.get('epoch')) is not int or command['epoch']<1:
            raise ValueError('Invalid assignment identity')
        if run_id is not None and not re.fullmatch('[a-f0-9]{32}',run_id):raise ValueError('Invalid run identity')
        recovery=command.get('recoveryIndex',0)
        if type(recovery) is not int or recovery not in (0,1):raise ValueError('Invalid recovery attempt')
        return self.root/'workers'/command['assignmentId']/f'r{recovery}'

    def _worker(self,command,action):
        directory=self.worker_directory(command)
        original=read_json(directory/'assignment.json')
        if action=='start':
            if not self.enabled:raise RuntimeError('Contribution is OFF for this boot')
            if command['workerId']!=self.config['workerId']:raise ValueError('Worker identity mismatch')
            if original and original!=command:raise ValueError('Frozen worker assignment changed')
            if original is None:
                # Persist ownership before launch so a lost ack is idempotent.
                write_json(directory/'assignment.json',command)
            argv=[sys.executable,str(ROOT/'scripts/run_worker.py'),'--coordinator-url',command['coordinatorUrl'],
                '--worker-id',self.config['workerId'],'--model-path',self.config['modelPath'],
                '--log',str(directory/'events.jsonl'),'--replay','always','--replay-verify-every','1',
                '--cache-dir',str(directory/'cache'),'--give-up-after-seconds','120','--chunk','16',
                '--stop-file',str(directory/'stop-request.json')]
            if (directory/'launch-intent.json').exists() and not (directory/'process.json').exists():
                raise RuntimeError('Worker launch ownership is unknown')
            write_json(directory/'launch-intent.json',{'started':True})
            return remote_handle({'action':'start','directory':str(directory),'source':str(ROOT/'src'),
                'token':command['computeToken'],'argv':argv})
        if original is None:return {'alive':False,'ready':False,'events':[]}
        result=remote_handle({'action':action,'directory':str(directory)})
        result['alive']=owned_state(read_json(directory/'process.json'),(directory/'launch-intent.json').exists())
        return result

    def handle(self,command):
        kind=command.get('kind')
        if kind not in {'SET_CONTRIBUTION','COORDINATE','START_WORKER','STOP_WORKER','CANCEL_ASSIGNMENT','UPDATE_BACKUP_POLICY'}:
            raise ValueError('Unsupported device command')
        cid=command.get('commandId')
        if not isinstance(cid,str) or not cid:raise ValueError('Missing command identity')
        with self.db() as db:
            if db.execute('SELECT 1 FROM processed WHERE id=?',(cid,)).fetchone():return
        if kind=='SET_CONTRIBUTION':
            if command['bootId']==self.boot_id:
                if command['enabled'] and self.shutdown_requested:raise RuntimeError('Desktop shutdown is pending')
                self.enabled=bool(command['enabled'])
                write_json(self.root/'boot.json',{'bootId':self.boot_id,'enabled':self.enabled})
                if not self.enabled:self.cancel_all()
        elif kind=='COORDINATE':
            if self.config.get('workerOnly'):
                raise ValueError('This device profile is worker-only')
            self.worker_directory(command)
            if self.cancelled(command):
                with self.db() as db:db.execute('INSERT OR IGNORE INTO processed VALUES (?)',(cid,))
                return
            if not self.enabled:raise RuntimeError('Contribution is OFF for this boot')
            if command['coordinatorDeviceId']!=self.config['deviceId']:raise ValueError('Coordinator identity mismatch')
            self.manager.accept(command)
        elif kind=='UPDATE_BACKUP_POLICY':
            self.worker_directory(command)
            matched=False
            for root in self.manager.root.iterdir():
                ar=read_json(root/'assignment.json') if root.is_dir() else None
                if ar and (ar['assignmentId'],ar['epoch'])==(command['assignmentId'],command['epoch']):
                    policy=command['policy']
                    if set(policy)!={'interval','retain'} or any(type(v) is not int or not 1<=v<=1000 for v in policy.values()):raise ValueError('Invalid backup policy')
                    write_json(root/'backup-policy.json',policy);matched=True
            if not matched:raise RuntimeError('Wait for the assignment before applying its policy')
        elif kind=='START_WORKER':
            self.worker_directory(command)
            if not self.cancelled(command):self._worker(command,'start')
        elif kind=='STOP_WORKER':self._worker(command,'stop')
        elif kind=='CANCEL_ASSIGNMENT':
            self.worker_directory(command)
            write_json(self.root/'cancelled-assignments'/f'{command["assignmentId"]}.json',{'assignmentId':command['assignmentId'],'epoch':command['epoch']})
            for root in self.manager.root.iterdir():
                ar=read_json(root/'assignment.json') if root.is_dir() else None
                if ar and (ar['assignmentId'],ar['epoch'])==(command['assignmentId'],command['epoch']):
                    self.manager.cancel(root.name)
            for directory in (self.root/'workers'/command['assignmentId']).glob('r*'):
                ar=read_json(directory/'assignment.json')
                if ar and ar['epoch']==command['epoch']:self._worker(ar,'stop')
        with self.db() as db:db.execute('INSERT OR IGNORE INTO processed VALUES (?)',(cid,))

    def cancelled(self,command):
        marker=read_json(self.root/'cancelled-assignments'/f'{command["assignmentId"]}.json')
        return marker and marker['epoch']==command['epoch']

    def cancel_all(self):
        for root in self.manager.root.iterdir():
            if root.is_dir() and read_json(root/'config.json') and self.manager.state(root).get('status') not in TERMINAL:
                self.manager.cancel(root.name)
        for directory in (self.root/'workers').glob('*/r*'):
            ar=read_json(directory/'assignment.json')
            if ar:self._worker(ar,'stop')

    def observe(self):
        combined={}
        with self.db() as db:released={r[0] for r in db.execute('SELECT assignment_id FROM released')}
        for root in self.manager.root.iterdir():
            ar=read_json(root/'assignment.json') if root.is_dir() else None
            if not ar:continue
            key=ar['assignmentId']
            if key in released:continue
            recovery=self.manager.state(root).get('recoveryCount',0)
            combined[key]={'assignmentId':key,'epoch':ar['epoch'],'coordinatorAlive':owned_state(read_json(root/'process.json'),(root/'launch-intent.json').exists()),
                           'workerAlive':None,'ready':False,'recoveryIndex':recovery,'events':[]}
            snap=self.manager.snapshot(root.name)
            # Keep a durable latest snapshot per assignment, not an unbounded copy
            # of the whole ledger projection every heartbeat during an outage.
            with self.db() as db:
                for event in snap['events']:
                    encoded=json.dumps(event,sort_keys=True,separators=(',',':'),allow_nan=False)
                    eid=hashlib.sha256((key+encoded).encode()).hexdigest()
                    db.execute('INSERT OR IGNORE INTO event_outbox(id,assignment_id,epoch,body) VALUES (?,?,?,?)',(eid,key,ar['epoch'],encoded))
            snap['events']=snap['events'][-2000:]
            snap['artifactContents']={}
            for artifact in snap['artifacts']:
                name=artifact['name'];path=root/name
                if path.is_file() and name.endswith(('.json','.jsonl')) and path.stat().st_size<=262144:
                    data=path.read_bytes()
                    snap['artifactContents'][name]={'base64':base64.b64encode(data).decode(),'sha256':hashlib.sha256(data).hexdigest()}
            snap['cloudSync']=read_json(root/'cloud-sync.json',{'status':'PENDING'})
            snap=bounded_snapshot(snap)
            with self.db() as db:
                row=db.execute('SELECT value FROM sequence WHERE assignment_id=?',(key,)).fetchone()
                sequence=(row[0] if row else 0)+1
                db.execute('INSERT OR REPLACE INTO sequence VALUES (?,?)',(key,sequence))
                report={'sequence':sequence,'assignmentId':key,'epoch':ar['epoch'],'snapshot':snap}
                db.execute('INSERT OR REPLACE INTO outbox VALUES (?,?,?)',(key,sequence,json.dumps(report)))
        for directory in (self.root/'workers').glob('*/r*'):
            ar=read_json(directory/'assignment.json')
            if not ar:continue
            key=ar['assignmentId']
            if key in released:continue
            p=self._worker(ar,'poll')
            old=combined.get(key)
            if old and ar['recoveryIndex']<old['recoveryIndex']:continue
            if not old or ar['recoveryIndex']>=old['recoveryIndex']:
                combined[key]={**(old or {'assignmentId':key,'epoch':ar['epoch'],'coordinatorAlive':False}),
                    'workerAlive':p['alive'],'ready':p['ready'],'recoveryIndex':ar['recoveryIndex'],'events':p['events'][-200:]}
        for path in (self.root/'cancelled-assignments').glob('*.json'):
            marker=read_json(path);key=marker['assignmentId']
            if key not in combined and key not in released:
                combined[key]={**marker,'coordinatorAlive':False,'workerAlive':False,'ready':False,'recoveryIndex':0,'events':[]}
        return list(combined.values())

    def cycle(self):
        processes=self.observe()
        with self.db() as db:
            reports=[json.loads(r[0]) for r in db.execute('SELECT body FROM outbox ORDER BY rowid LIMIT 1')]
            event_batch=[{'eventId':r[0],'assignmentId':r[1],'epoch':r[2],'event':json.loads(r[3])} for r in db.execute('SELECT id,assignment_id,epoch,body FROM event_outbox WHERE ack=0 ORDER BY rowid LIMIT 500')]
            while len(json.dumps(event_batch).encode())>512_000:
                event_batch=event_batch[:max(0,len(event_batch)//2)]
            acknowledgements=[r[0] for r in db.execute('SELECT id FROM processed ORDER BY rowid DESC LIMIT 100')]
        response=self.call('/api/v1/device/poll',{'bootId':self.boot_id,'contribution':self.enabled,
            'processes':processes[:10],'reports':reports,'events':event_batch,'acknowledgements':acknowledgements,
            **({'selfTest':self.config['selfTest']} if self.config.get('selfTest') else {})})
        # The first poll of a new boot always returns OFF. A user-authenticated
        # activation or typed command for the current boot is needed before launch.
        if response['approvalStatus']=='REVOKED' or (self.enabled and not response['desiredContribution']):
            self.enabled=False;self.cancel_all()
        for command in response['commands']:
            try:self.handle(command)
            except RuntimeError:pass  # OFF/deferred commands remain unacknowledged
        with self.db() as db:
            for eid in response.get('acceptedEvents',[]):db.execute('UPDATE event_outbox SET ack=1 WHERE id=?',(eid,))
            for aid in response.get('releasedAssignments',[]):db.execute('INSERT OR IGNORE INTO released VALUES (?)',(aid,))
            for accepted in response['acceptedReports']:
                db.execute('DELETE FROM outbox WHERE assignment_id=? AND sequence=?',(accepted['assignmentId'],accepted['sequence']))
        return response

    def run(self):
        if self.instance_lock is None:
            self.instance_lock=acquire_instance_lock(self.root/'agent.lock')
        self.manager.thread.start()
        from .cloud_sync import CloudSync
        self.cloud_sync=CloudSync(self);self.cloud_sync.thread.start()
        while not self.stopping:
            try:
                with self.desktop_lock:self.cycle()
                write_json(self.root/'connection.json',{'status':'ONLINE','t':time.time()})
            except Exception as error:
                write_json(self.root/'connection.json',{'status':'OFFLINE','errorType':type(error).__name__,'t':time.time()})
            for _ in range(100):
                if self.stopping:break
                time.sleep(.1)
        self.cloud_sync.stop.set();self.cloud_sync.thread.join(timeout=2)
        self.manager.stop.set();self.manager.thread.join(timeout=2)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['run','on','off','status','enroll'])
    parser.add_argument('--config',required=True,type=Path)
    args=parser.parse_args();config=read_json(args.config)
    if args.action=='enroll':
        # Run the compatibility gate in a separate GPU process with the same
        # process-local WSL libraries used for actual workers.
        from .remote import worker_environment
        import subprocess
        code=getpass.getpass('One-use pairing code: ')
        env=worker_environment(str(ROOT/'src'),'self-test-no-network')
        result=subprocess.run([sys.executable,'-m','heteroes.product.selftest',config['modelPath']],env=env,capture_output=True,text=True,timeout=300)
        if result.returncode:raise SystemExit('Device self-test failed; inspect the local GPU environment')
        test=json.loads(result.stdout.splitlines()[-1])
        paired=request(config['serverUrl'],'/api/v1/device/enroll','',{'code':code,'workerId':config['workerId'],
            'displayName':config.get('displayName',config['workerId']),'computeUrl':config['computeUrl'],'selfTest':test})
        config.update(deviceId=paired['deviceId'],deviceToken=paired['deviceToken'],selfTest=test);write_json(args.config,config)
        print('Enrolled; administrator approval required. Contribution is OFF.')
    elif args.action=='run':
        agent=Agent(args.config,lock=True)
        def stop(*_):agent.stopping=True
        signal.signal(signal.SIGINT,stop);signal.signal(signal.SIGTERM,stop)
        agent.run()
    elif args.action=='status':
        boot=read_json(Path(config['stateDirectory'])/'boot.json',{})
        connection=read_json(Path(config['stateDirectory'])/'connection.json',{})
        print(json.dumps({'workerId':config['workerId'],'deviceId':config.get('deviceId'),'boot':boot,'connection':connection},indent=2))
    else:
        username=input('Owner username: ');password=getpass.getpass('Owner password: ')
        session=request(config['serverUrl'],'/api/v1/auth/login','',{'username':username,'password':password})
        boot=read_json(Path(config['stateDirectory'])/'boot.json')
        request(config['serverUrl'],'/api/v1/devices/'+config['deviceId']+'/contribution',session['accessToken'],
            {'enabled':args.action=='on','bootId':boot['bootId']})
        request(config['serverUrl'],'/api/v1/auth/logout',session['accessToken'],{})
        print('Contribution change requested for the current boot.')


if __name__=='__main__':main()
