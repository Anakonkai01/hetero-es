"""CPU-only device control. Connectivity is never evidence of process death."""
import hashlib
import json
import os
from pathlib import Path
import secrets
import time
import uuid
from typing import Literal
from urllib.parse import urlparse
import ipaddress

from fastapi import Depends, Header, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from .runtime import RuntimeRejected
from .monitor_models import Core, Interface, BlockDevice, HostProcess, GPUProcess, Sensor, Power
from .addresses import endpoint, is_private
from .study.data import sha as study_hash

TERMINAL = {'COMPLETED', 'CANCELLED', 'FAILED'}
QUIESCENT = TERMINAL | {'PAUSED'}
MODEL = 'Qwen/Qwen2.5-0.5B-Instruct'
REVISION = '7ae557604adf67be50417f59c2c2f167def9a775'


def re_checkpoint(name):
    import re
    return re.fullmatch(r'[a-f0-9]{64}\.bin',name)


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)


class SelfTest(Strict):
    passed: bool
    coordinator: bool = False
    gpuName: str = Field(max_length=200)
    vramTotalMb: int = Field(ge=1, le=1000000)
    noiseVersion: Literal['numpy_pcg64_normal_f32_to_f16_v1']
    environment: dict = Field(default_factory=dict)
    platform: Literal['linux','windows'] = 'linux'
    runtimeProfile: str = Field(default='legacy', max_length=100)
    compatibility: dict = Field(default_factory=dict)
    gpuUUID: str | None = None
    recipeVersions: list[Literal[1,2]] = Field(default_factory=lambda:[1],max_length=2)
    qualifiedModelHashes: list[str] = Field(default_factory=list,max_length=20)

    @field_validator('gpuUUID')
    @classmethod
    def physical_gpu(cls, value):
        if value is None:
            return value
        if not value.startswith('GPU-'):
            raise ValueError('Use the NVIDIA physical GPU UUID')
        try:
            return 'GPU-' + str(uuid.UUID(value[4:]))
        except (ValueError, AttributeError):
            raise ValueError('Invalid physical GPU UUID') from None

    @model_validator(mode='after')
    def native_admission(self):
        import re
        if any(not re.fullmatch('[a-f0-9]{64}',h) for h in self.qualifiedModelHashes):raise ValueError('Invalid model qualification hash')
        if 2 in self.recipeVersions:
            evidence=self.compatibility.get('recipeV2',{})
            if not self.passed or evidence.get('passed') is not True or evidence.get('repeatIdentical') is not True:
                raise ValueError('Recipe v2 requires repeated numerical compatibility evidence')
            if any(not re.fullmatch('[a-f0-9]{64}',str(evidence.get(k,''))) for k in ('modelManifestHash','recipeHash','parentSha256','restoredSha256','perturbedSha256','outputsHash')) or evidence['parentSha256']!=evidence['restoredSha256']:
                raise ValueError('Recipe v2 compatibility identity or exact restore mismatch')
            if evidence['modelManifestHash'] not in self.qualifiedModelHashes:raise ValueError('Recipe v2 model qualification missing')
        if self.platform == 'windows':
            if self.recipeVersions != [1] or self.qualifiedModelHashes:raise ValueError('Windows remains the qualified v1 worker-only profile')
            if not self.passed or self.coordinator or self.runtimeProfile != 'desktop-v1' or self.compatibility.get('passed') is not True or self.compatibility.get('repeatIdentical') is not True:
                raise ValueError('Native Windows requires the qualified worker-only desktop profile')
            for key in ('recipeHash','parentSha256','perturbedSha256','restoredSha256'):
                import re
                if not re.fullmatch(r'[a-f0-9]{64}',str(self.compatibility.get(key,''))):
                    raise ValueError('Missing native compatibility evidence')
            if self.compatibility['parentSha256'] != self.compatibility['restoredSha256']:
                raise ValueError('Native candidate restore mismatch')
            if self.compatibility.get('predictionProbePassed') is not True or self.compatibility.get('probeOutputsSha256') != '5601ce2d20cc290f9dd8d84ff3988b15a4191fb02411a2e72805af66bf5e31b4':
                raise ValueError('Native Windows requires the Linux prediction probe')
            reference = {'recipeHash': 'efc1ff67c1bfa8c243ba93ce4a46dfcea74e5afc4b2daffa50498510d53dbc86', 'parentSha256': 'c9118c8a4903c0a84700deeaf7b1929c354dfcf6d6805c08d9afb22cfd5d22c7', 'perturbedSha256': 'd3e35e5984684a4f76c7ec2eeba10ff8afe0483721582c52013a06e5819a9c2c', 'restoredSha256': 'c9118c8a4903c0a84700deeaf7b1929c354dfcf6d6805c08d9afb22cfd5d22c7', 'reward': 0.1875}
            if any(self.compatibility.get(k) != value for k,value in reference.items()):
                raise ValueError('Native profile does not match the qualified Linux reference')
        return self


class EndpointUpdate(Strict):
    computeUrl: str
    bulkUrl: str | None = None

    @field_validator('computeUrl')
    @classmethod
    def control(cls, value):
        return endpoint(value)

    @field_validator('bulkUrl')
    @classmethod
    def bulk(cls, value):
        return endpoint(value, private=True) if value is not None else None

    @model_validator(mode='after')
    def private_bulk_required(self):
        if self.bulkUrl is None and not is_private(self.computeUrl):
            raise ValueError('Public compute requires a private bulkUrl')
        return self


class DeviceEndpointUpdate(EndpointUpdate):
    bootId: str = Field(min_length=1, max_length=100)


class QualificationUpdate(Strict):
    bootId: str
    selfTest: SelfTest


class Enrollment(EndpointUpdate):
    code: str = Field(max_length=200)
    workerId: str = Field(min_length=1, max_length=64, pattern=r'^[a-zA-Z0-9][a-zA-Z0-9_-]*$')
    displayName: str = Field(min_length=1, max_length=100)
    selfTest: SelfTest

    @staticmethod
    def private_compute(value):
        # Kept strict for Server bootstrap and LocalBackend signed URLs.
        return endpoint(value, private=True)


class Approval(Strict):
    approved: bool
    workspaceId: str | None = None


class Contribution(Strict):
    enabled: bool
    bootId: str = Field(min_length=1, max_length=100)


class ProcessReport(Strict):
    assignmentId: str
    epoch: int = Field(ge=1)
    coordinatorAlive: bool | None = None
    workerAlive: bool | None = None
    ready: bool = False
    recoveryIndex: int = Field(default=0, ge=0, le=1)
    events: list[dict] = Field(default_factory=list, max_length=200)


class Report(Strict):
    sequence: int = Field(ge=1)
    assignmentId: str
    epoch: int = Field(ge=1)
    snapshot: dict


class MonitoringEvent(Strict):
    eventId:str
    assignmentId:str
    epoch:int=Field(ge=1)
    event:dict


class GPUObservation(Strict):
    uuid: str = Field(max_length=100)
    name: str = Field(max_length=200)
    utilizationPercent: float | None = Field(default=None,ge=0,le=100)
    temperatureC: float | None = Field(default=None,ge=0,le=200)
    vramTotalMb: float | None = Field(default=None,ge=0,le=1000000)
    vramUsedMb: float | None = Field(default=None,ge=0,le=1000000)
    powerDrawW: float | None = Field(default=None,ge=0,le=10000)
    powerLimitW: float | None = Field(default=None,ge=0,le=10000)
    fanPercent: float | None = Field(default=None,ge=0,le=100)
    clockMhz: float | None = Field(default=None,ge=0,le=100000)
    memoryUtilizationPercent: float | None = Field(default=None,ge=0,le=100)
    memoryClockMhz: float | None = Field(default=None,ge=0,le=100000)
    performanceState: str | None = Field(default=None,max_length=30)
    pcieGeneration: float | None = Field(default=None,ge=0,le=100)
    pcieWidth: float | None = Field(default=None,ge=0,le=100)
    processes: list[GPUProcess] = Field(default_factory=list,max_length=64)
    energyWh: float | None = Field(default=None,ge=0)
    energySampledSeconds: float = Field(default=0,ge=0)

class HostObservation(Strict):
    uptimeSeconds: float | None = Field(default=None,ge=0)
    cpuModel: str | None = Field(default=None,max_length=200)
    cores: list[Core] = Field(default_factory=list,max_length=512)
    networkInterfaces: list[Interface] = Field(default_factory=list,max_length=32)
    blockDevices: list[BlockDevice] = Field(default_factory=list,max_length=32)
    processes: list[HostProcess] = Field(default_factory=list,max_length=20)
    sensors: list[Sensor] = Field(default_factory=list,max_length=128)
    processCount: int | None = Field(default=None,ge=0)
    ramAvailableBytes: int | None = Field(default=None,ge=0)
    ramCachedBytes: int | None = Field(default=None,ge=0)
    ramBuffersBytes: int | None = Field(default=None,ge=0)
    ramDirtyBytes: int | None = Field(default=None,ge=0)
    cpuCount: int | None = Field(default=None,ge=1,le=100000)
    platform: str = Field(max_length=30)
    cpuPercent: float | None = Field(default=None,ge=0,le=100)
    ramTotalBytes: int | None = Field(default=None,ge=0)
    ramUsedBytes: int | None = Field(default=None,ge=0)
    swapTotalBytes: int | None = Field(default=None,ge=0)
    swapUsedBytes: int | None = Field(default=None,ge=0)
    networkRxBytesPerSecond: float | None = Field(default=None,ge=0)
    networkTxBytesPerSecond: float | None = Field(default=None,ge=0)
    diskReadBytesPerSecond: float | None = Field(default=None,ge=0)
    diskWriteBytesPerSecond: float | None = Field(default=None,ge=0)
    loadAverage: list[float] = Field(default_factory=list,max_length=3)

class DiskObservation(Strict):
    label: Literal['state','artifacts']
    totalBytes: int = Field(ge=0)
    usedBytes: int = Field(ge=0)
    freeBytes: int = Field(ge=0)

class TransportObservation(Strict):
    latencyMs: float | None = Field(default=None,ge=0)
    pendingReports: int = Field(default=0,ge=0)
    pendingEvents: int = Field(default=0,ge=0)

class Telemetry(Strict):
    power: Power | None = None
    transport: TransportObservation | None = None
    sampledAt: float = Field(ge=0)
    sessionStartedAt: float = Field(ge=0)
    source: Literal['host-observation']
    host: HostObservation | None = None
    gpu: GPUObservation | None = None
    disks: list[DiskObservation] = Field(default_factory=list,max_length=2)
    errors: list[str] = Field(default_factory=list,max_length=5)

class Poll(Strict):
    telemetry: Telemetry | None = None
    bootId: str = Field(min_length=1, max_length=100)
    contribution: bool = False
    processes: list[ProcessReport] = Field(default_factory=list, max_length=10)
    reports: list[Report] = Field(default_factory=list, max_length=20)
    events:list[MonitoringEvent]=Field(default_factory=list,max_length=500)
    acknowledgements: list[str] = Field(default_factory=list, max_length=100)
    selfTest: SelfTest | None = None


class WorkerCommand(Strict):
    assignmentId: str
    epoch: int = Field(ge=1)
    workerId: str
    action: Literal['start', 'poll', 'stop', 'probe']
    recoveryIndex: int = Field(default=0, ge=0, le=1)


class AgentRuntime:
    """Adapter for the existing product dispatcher; no Track A imports on the server."""
    agent_mode = True

    def __init__(self, storage_backend=None):
        self.store = None
        self.storage_backend = storage_backend

    def attach_store(self, store):
        self.store = store
        with store.db() as db:
            db.execute('INSERT OR REPLACE INTO settings VALUES (?,?)',('controlMode','agent-v2'))
            db.executescript('''
                CREATE TABLE IF NOT EXISTS pairing_codes (digest TEXT PRIMARY KEY,owner TEXT NOT NULL,expires REAL NOT NULL,used INTEGER NOT NULL DEFAULT 0);
                CREATE TABLE IF NOT EXISTS devices (id TEXT PRIMARY KEY,worker_id TEXT UNIQUE NOT NULL,owner TEXT NOT NULL,name TEXT NOT NULL,token_digest TEXT NOT NULL,status TEXT NOT NULL,compute_url TEXT NOT NULL,self_test TEXT NOT NULL,boot_id TEXT,seen REAL NOT NULL DEFAULT 0,enabled INTEGER NOT NULL DEFAULT 0,desired INTEGER NOT NULL DEFAULT 0,processes TEXT NOT NULL DEFAULT '[]');
                CREATE TABLE IF NOT EXISTS assignments (id TEXT PRIMARY KEY,run_id TEXT UNIQUE NOT NULL,coordinator TEXT NOT NULL,epoch INTEGER NOT NULL,body TEXT NOT NULL,snapshot TEXT NOT NULL,released INTEGER NOT NULL DEFAULT 0);
                CREATE TABLE IF NOT EXISTS device_reservations (device_id TEXT PRIMARY KEY,assignment_id TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS physical_reservations (resource_id TEXT PRIMARY KEY,assignment_id TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS device_commands (id TEXT PRIMARY KEY,device_id TEXT NOT NULL,dedupe TEXT NOT NULL UNIQUE,body TEXT NOT NULL,ack INTEGER NOT NULL DEFAULT 0,created REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS monitoring_events(sequence INTEGER PRIMARY KEY AUTOINCREMENT,event_id TEXT UNIQUE NOT NULL,assignment_id TEXT NOT NULL,body TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS device_telemetry_history(device_id TEXT NOT NULL,boot_id TEXT NOT NULL,sampled_at REAL NOT NULL,received_at REAL NOT NULL,body TEXT NOT NULL,PRIMARY KEY(device_id,boot_id,sampled_at));
                CREATE TABLE IF NOT EXISTS device_reports (device_id TEXT NOT NULL,assignment_id TEXT NOT NULL,sequence INTEGER NOT NULL,PRIMARY KEY(device_id,assignment_id,sequence));
            ''')
            if 'telemetry' not in {r[1] for r in db.execute('PRAGMA table_info(devices)')}:
                db.execute("ALTER TABLE devices ADD COLUMN telemetry TEXT")
            if 'bulk_url' not in {r[1] for r in db.execute('PRAGMA table_info(devices)')}:
                db.execute('ALTER TABLE devices ADD COLUMN bulk_url TEXT')
            # Retain every assignment epoch. The old unique run_id constraint
            # cannot represent a paused run reacquiring resources with fresh
            # commands, credentials and process identities.
            schema=db.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='assignments'").fetchone()[0]
            if 'run_id TEXT UNIQUE' in schema:
                db.executescript('''
                    BEGIN IMMEDIATE;
                    ALTER TABLE assignments RENAME TO assignments_v2;
                    CREATE TABLE assignments(id TEXT PRIMARY KEY,run_id TEXT NOT NULL,coordinator TEXT NOT NULL,
                        epoch INTEGER NOT NULL,body TEXT NOT NULL,snapshot TEXT NOT NULL,released INTEGER NOT NULL DEFAULT 0);
                    INSERT INTO assignments SELECT * FROM assignments_v2;
                    DROP TABLE assignments_v2;
                    COMMIT;
                ''')
            db.execute('CREATE UNIQUE INDEX IF NOT EXISTS active_assignment_per_run ON assignments(run_id) WHERE released=0')
            db.execute('CREATE UNIQUE INDEX IF NOT EXISTS assignment_epoch ON assignments(run_id,epoch)')
            for row in db.execute('SELECT r.assignment_id,d.self_test FROM device_reservations r JOIN devices d ON d.id=r.device_id').fetchall():
                resource = json.loads(row['self_test']).get('gpuUUID')
                if resource:
                    old = db.execute('SELECT assignment_id FROM physical_reservations WHERE resource_id=?',(resource,)).fetchone()
                    if old and old[0] != row['assignment_id']:
                        raise RuntimeError('Conflicting physical GPU ownership; keep dispatch held')
                    db.execute('INSERT OR IGNORE INTO physical_reservations VALUES (?,?)',(resource,row['assignment_id']))

    def devices(self, db=None):
        if self.store is None:
            return []
        if db is None:
            with self.store.db() as connection:
                return self.devices(connection)
        result=[]
        for row in db.execute('SELECT * FROM devices ORDER BY rowid'):
            profile=json.loads(row['self_test'])
            reservation=db.execute('SELECT a.run_id FROM device_reservations r JOIN assignments a ON a.id=r.assignment_id WHERE r.device_id=?',(row['id'],)).fetchone()
            if not reservation and profile.get('gpuUUID'):
                reservation=db.execute('SELECT a.run_id FROM physical_reservations r JOIN assignments a ON a.id=r.assignment_id WHERE r.resource_id=?',(profile['gpuUUID'],)).fetchone()
            allocation=db.execute('SELECT workspace_id FROM worker_assignments WHERE worker_id=?',(row['worker_id'],)).fetchone()
            result.append({'deviceId':row['id'],'workerId':row['worker_id'],'ownerUserId':row['owner'],
                          'displayName':row['name'],'approvalStatus':row['status'],'bootId':row['boot_id'],
                          'lastSeen':row['seen'],'connectionStatus':'ONLINE' if time.time()-row['seen']<30 else 'OFFLINE',
                          'contributionEnabled':bool(row['enabled'] and row['desired']),
                          'workspaceId':allocation[0] if allocation else None,'computeUrl':row['compute_url'],
                          'bulkUrl':row['bulk_url'] or row['compute_url'],
                          'selfTest':profile, 'allocatedTo':reservation[0] if reservation else None,
                          'physicalResourceId':profile.get('gpuUUID'),
                          'telemetry':json.loads(row['telemetry']) if row['telemetry'] else None,
                          'telemetryHistory':[json.loads(h[0]) for h in db.execute('SELECT body FROM device_telemetry_history WHERE device_id=? ORDER BY received_at DESC LIMIT 60',(row['id'],)).fetchall()][::-1]})
        return result

    def capabilities(self):
        return {'controlApiVersion':2,'recipeVersions':[1,2],'agentMode':True,'physicalGpuIdentity':True,'parallelJobs':True,'modelId':MODEL,'modelRevision':REVISION,
                'workerIds':[d['workerId'] for d in self.devices() if d['approvalStatus']=='APPROVED'],
                'workloads':['arith16','cot_l3_q32','cot_l3_q64','cot_l1_q128'],
                'schedulerPolicies':['greedy'],'syncModes':['synchronous'],'quarantinedWorkerIds':[d['workerId'] for d in self.devices() if d['approvalStatus']=='QUARANTINED'],
                'maxRunSeconds':None,'telemetry':True,'pauseResume':True,'unsupported':['change-workers','model-upload','dataset-upload','asynchronous']}

    def public_compute_url(self):
        """The lab's public compute address, read per command so a new Quick URL is used at once.
        Only a public HTTPS host name is passed on; anything else is ignored."""
        root=os.environ.get('HETEROES_PRIVATE_CONFIG')
        if not root:return None
        try:
            value=json.loads((Path(root)/'config.json').read_text()).get('publicComputeUrl')
            return endpoint(value) if value and not is_private(value) else None
        except (OSError,ValueError,TypeError):
            return None

    def workers(self):
        return [{**d,'status':d['connectionStatus'],'host':d['computeUrl'],'profile':{**d['selfTest'],
                 **({'vramFreeMb':max(0,d['telemetry']['gpu']['vramTotalMb']-d['telemetry']['gpu']['vramUsedMb'])} if d.get('telemetry') and d['telemetry'].get('gpu') and d['telemetry']['gpu'].get('vramTotalMb') is not None and d['telemetry']['gpu'].get('vramUsedMb') is not None else {})},
                 'temperatureC':(d.get('telemetry') or {}).get('gpu',{}).get('temperatureC') if (d.get('telemetry') or {}).get('gpu') else None,
                 'utilizationPercent':(d.get('telemetry') or {}).get('gpu',{}).get('utilizationPercent') if (d.get('telemetry') or {}).get('gpu') else None,
                 'admissionStatus':'APPROVED' if d['approvalStatus']=='APPROVED' else 'PENDING_VERIFICATION'} for d in self.devices()]

    def waiting_reason(self, body, db=None):
        if db is None:
            with self.store.db() as connection:
                return self.waiting_reason(body, connection)
        devices=self.devices(db);by_id={d['deviceId']:d for d in devices};by_worker={d['workerId']:d for d in devices}
        coordinator=by_id.get(body.get('coordinatorDeviceId'))
        if not coordinator or not coordinator['selfTest'].get('coordinator'):
            return 'Select an approved coordinator device'
        chosen=[coordinator]+[by_worker.get(w) for w in body['workerIds']]
        for d in chosen:
            if not d or d['approvalStatus']!='APPROVED':return 'Selected device needs approval'
            if body.get('recipeVersion')==2:
                profile=d['selfTest']
                if profile.get('platform')=='windows' or 2 not in profile.get('recipeVersions',[]):return 'Recipe v2 qualification required'
                if study_hash(body['modelManifest']) not in profile.get('qualifiedModelHashes',[]):return 'Pinned model qualification required'
            if not d['physicalResourceId']:return 'Refresh selected device self-test to identify its physical GPU'
            if d['connectionStatus']!='ONLINE':return 'Waiting for selected device to reconnect'
            if not d['contributionEnabled']:return 'Waiting for owner to turn contribution ON'
            if d['allocatedTo'] and d['allocatedTo']!=body['experimentId']:return 'Waiting for confirmed GPU release'
            reservation=db.execute('SELECT a.run_id FROM physical_reservations r JOIN assignments a ON a.id=r.assignment_id WHERE resource_id=?',(d['physicalResourceId'],)).fetchone()
            if reservation and reservation[0]!=body['experimentId']:return 'Waiting for confirmed physical GPU release'
        # An old assignment lacking a UUID may be the same GPU as a new alias.
        for reserved in db.execute('SELECT d.self_test FROM device_reservations r JOIN devices d ON d.id=r.device_id'):
            if not json.loads(reserved[0]).get('gpuUUID'):
                return 'Waiting for legacy ownership release before physical GPU scheduling'
        workers=[by_worker[w]['physicalResourceId'] for w in body['workerIds']]
        if len(set(workers))!=len(workers):
            return 'Selected worker aliases refer to the same physical GPU'
        return None

    def _enqueue(self, db, device_id, kind, body, dedupe):
        cid=uuid.uuid4().hex
        message={'commandId':cid,'kind':kind,**body}
        db.execute('INSERT OR IGNORE INTO device_commands VALUES (?,?,?,?,0,?)',
                   (cid,device_id,dedupe,json.dumps(message,allow_nan=False),time.time()))

    def commands(self, device_id):
        with self.store.db() as db:
            result=[]
            for row in db.execute('SELECT body FROM device_commands WHERE device_id=? AND ack=0 ORDER BY created',(device_id,)):
                command=json.loads(row[0])
                if command['kind'] in ('COORDINATE','START_WORKER','PAUSE_ASSIGNMENT','UPDATE_BACKUP_POLICY'):
                    assignment=db.execute('SELECT released FROM assignments WHERE id=? AND epoch=?',
                        (command['assignmentId'],command['epoch'])).fetchone()
                    if not assignment or assignment['released']:continue
                result.append(command)
            return result

    def reservations(self):
        with self.store.db() as db:
            return [{'deviceId':r['device_id'],'assignmentId':r['assignment_id']} for r in db.execute('SELECT * FROM device_reservations')]

    def _assignment(self, db, assignment_id):
        row=db.execute('SELECT * FROM assignments WHERE id=?',(assignment_id,)).fetchone()
        if not row:raise HTTPException(404,'Assignment not found')
        return row,json.loads(row['body'])

    def submit(self, config):
        with self.store.db() as db:
            db.execute('BEGIN IMMEDIATE')
            old=db.execute('SELECT * FROM assignments WHERE run_id=? ORDER BY epoch DESC LIMIT 1',(config['runId'],)).fetchone()
            body=self.store.get(config['runId'])
            if old:
                if json.loads(old['body'])['config']!=config:raise RuntimeRejected('Frozen assignment cannot change')
                if not body.get('resumeRequested'):return
                if not old['released'] or json.loads(old['snapshot'])['state']['status']!='PAUSED':
                    raise RuntimeRejected('Resume requires a released paused assignment')
            if reason:=self.waiting_reason(body, db):raise ConnectionError(reason)
            devices=self.devices(db);by_id={d['deviceId']:d for d in devices};by_worker={d['workerId']:d for d in devices}
            co=by_id[config['coordinatorDeviceId']]
            chosen={d['deviceId']:d for d in [co]+[by_worker[w] for w in config['workerIds']]}
            aid=uuid.uuid4().hex
            # Secrets are random per device/run, stored only in the private product DB.
            grants={d['workerId']:secrets.token_urlsafe(32) for d in chosen.values() if d['workerId'] in config['workerIds']}
            assignment={'assignmentId':aid,'runId':config['runId'],'coordinatorDeviceId':co['deviceId'],
                        'epoch':old['epoch']+1 if old else 1,'deviceIds':list(chosen),'config':config,'computeUrl':co['computeUrl'],
                        'bulkUrl':co['bulkUrl'],
                        'workerDevices':{w:by_worker[w]['deviceId'] for w in config['workerIds']},'computeGrants':grants}
            snap={'state':{'status':'STARTING'},'generations':[],'candidates':[],'attempts':[],'events':[],'artifacts':[]}
            if old:
                prior=json.loads(old['snapshot'])
                assignment['resumeFrom']=prior['state']['pauseCheckpoint']
                snap={**prior,'state':{'status':'STARTING'}}
            db.execute('INSERT INTO assignments VALUES (?,?,?,?,?,?,0)',(aid,config['runId'],co['deviceId'],assignment['epoch'],json.dumps(assignment),json.dumps(snap)))
            for did in chosen:db.execute('INSERT INTO device_reservations VALUES (?,?)',(did,aid))
            for resource in {d['physicalResourceId'] for d in chosen.values()}:
                db.execute('INSERT INTO physical_reservations VALUES (?,?)',(resource,aid))
            self._enqueue(db,co['deviceId'],'COORDINATE',{**assignment,'effectiveBackupPolicy':body.get('requestedBackupPolicy') or config['backupPolicy']},'coordinate:'+aid)
            body['resumeRequested']=False
            body['pauseRequested']=False
            self.store.save(db,body)
            self.store.audit(db,'system','ASSIGNMENT_CREATED',aid,body['workspaceId'])

    def snapshot(self, run_id):
        with self.store.db() as db:
            row=db.execute('SELECT snapshot,released FROM assignments WHERE run_id=? ORDER BY epoch DESC LIMIT 1',(run_id,)).fetchone()
            if not row:raise FileNotFoundError(run_id)
            snap=json.loads(row[0])
            if not row[1] and snap['state']['status'] in QUIESCENT:
                snap['state']={**snap['state'],'status':'PAUSING' if snap['state']['status']=='PAUSED' else 'DRAINING'}
            return snap

    def runs(self):
        if not self.store:return []
        with self.store.db() as db:
            return [{'runId':r['run_id'],'assignmentId':r['id'],'epoch':r['epoch'],
                     'status':json.loads(r['snapshot'])['state']['status'] if r['released'] else self.snapshot(r['run_id'])['state']['status']}
                    for r in db.execute('SELECT * FROM assignments ORDER BY rowid')]

    def cancel(self, run_id, db=None):
        if db is None:
            with self.store.db() as connection:
                return self.cancel(run_id, connection)
        if True:
            row=db.execute('SELECT id,body,released FROM assignments WHERE run_id=? ORDER BY epoch DESC LIMIT 1',(run_id,)).fetchone()
            if not row or row['released']:return
            ar=json.loads(row['body'])
            for did in ar['deviceIds']:
                self._enqueue(db,did,'CANCEL_ASSIGNMENT',{'assignmentId':ar['assignmentId'],'epoch':ar['epoch']},'cancel:'+ar['assignmentId']+':'+did)

    def pause(self,run_id):
        with self.store.db() as db:
            row=db.execute('SELECT * FROM assignments WHERE run_id=? ORDER BY epoch DESC LIMIT 1',(run_id,)).fetchone()
            if not row or row['released']:return
            self._enqueue(db,row['coordinator'],'PAUSE_ASSIGNMENT',
                {'assignmentId':row['id'],'epoch':row['epoch']},'pause:'+row['id'])

    def _release_confirmed(self, db, row, ar):
        snap=json.loads(row['snapshot'])
        if row['released'] or snap['state'].get('status') not in QUIESCENT:return
        for did in ar['deviceIds']:
            d=db.execute('SELECT processes,seen FROM devices WHERE id=?',(did,)).fetchone()
            reports=[p for p in json.loads(d[0]) if p['assignmentId']==ar['assignmentId'] and p['epoch']==ar['epoch']]
            if time.time()-d['seen']>=30 or len(reports)!=1:return
            p=reports[0]
            if did==ar['coordinatorDeviceId'] and p.get('coordinatorAlive') is not False:return
            if did in ar['workerDevices'].values() and p.get('workerAlive') is not False:return
        db.execute('UPDATE assignments SET released=1 WHERE id=?',(ar['assignmentId'],))
        db.execute('DELETE FROM device_reservations WHERE assignment_id=?',(ar['assignmentId'],))
        db.execute('DELETE FROM physical_reservations WHERE assignment_id=?',(ar['assignmentId'],))

    def poll(self, device, body):
        with self.store.db() as db:
            old=db.execute('SELECT * FROM devices WHERE id=?',(device['id'],)).fetchone()
            if body.selfTest is not None:
                previous=json.loads(old['self_test'])
                updated=body.selfTest.model_dump()
                reserved=db.execute('SELECT 1 FROM device_reservations WHERE device_id=?',(device['id'],)).fetchone()
                if reserved and updated.get('gpuUUID')!=previous.get('gpuUUID'):
                    raise HTTPException(409,'Physical GPU identity cannot change during ownership')
                if not updated['passed']:
                    raise HTTPException(422,'Self-test refresh must pass qualification')
                db.execute('UPDATE devices SET self_test=? WHERE id=?',(json.dumps(updated),device['id']))
            if body.telemetry is not None:
                observation=body.telemetry.model_dump(exclude_none=True)
                profile=json.loads(old['self_test'])
                if observation.get('gpu') and profile.get('gpuUUID') and observation['gpu']['uuid']!=profile['gpuUUID']:
                    raise HTTPException(422,'Telemetry GPU differs from qualified physical GPU')
                observation['receivedAt']=time.time()
                db.execute('UPDATE devices SET telemetry=? WHERE id=?',(json.dumps(observation),device['id']))
                gpu=observation.get('gpu',{});host=observation.get('host',{})
                power=observation.get('power') or {}
                packages=[c['powerW'] for c in power.get('components',[]) if c['kind']=='cpu-package' and c.get('powerW') is not None]
                point={'at':observation['receivedAt'],'cpuPowerW':sum(packages) if packages else None,
                       'componentPowerW':power.get('componentSubtotalW'),'wholeMachineW':power.get('wholeMachineW'),
                       'gpuPowerW':gpu.get('powerDrawW'),
                       'temperatureC':gpu.get('temperatureC'),'gpuPercent':gpu.get('utilizationPercent'),
                       'cpuPercent':host.get('cpuPercent'),'vramUsedMb':gpu.get('vramUsedMb'),
                       'ramUsedBytes':host.get('ramUsedBytes')}
                db.execute('INSERT OR IGNORE INTO device_telemetry_history VALUES (?,?,?,?,?)',
                    (device['id'],body.bootId,observation['sampledAt'],observation['receivedAt'],json.dumps(point)))
                db.execute('DELETE FROM device_telemetry_history WHERE device_id=? AND rowid NOT IN (SELECT rowid FROM device_telemetry_history WHERE device_id=? ORDER BY received_at DESC LIMIT 180)',(device['id'],device['id']))
            elif old['boot_id']!=body.bootId:
                db.execute('UPDATE devices SET telemetry=NULL WHERE id=?',(device['id'],))
            changed=old['boot_id']!=body.bootId
            desired=0 if changed else old['desired']
            # ON must be requested through owner auth and observed on this same boot.
            enabled=bool(desired and body.contribution)
            db.execute('UPDATE devices SET boot_id=?,seen=?,enabled=?,desired=?,processes=? WHERE id=?',
                       (body.bootId,time.time(),enabled,desired,json.dumps([p.model_dump() for p in body.processes]),device['id']))
            if changed:
                db.execute("UPDATE device_commands SET ack=1 WHERE device_id=? AND json_extract(body,'$.kind')='SET_CONTRIBUTION'",(device['id'],))
                # Cancellation remains authoritative across agent boots, including
                # when an old boot acknowledged it before a process-state report.
                for assignment in db.execute('SELECT a.* FROM assignments a JOIN device_reservations r ON r.assignment_id=a.id WHERE r.device_id=?',(device['id'],)).fetchall():
                    run=self.store.get(assignment['run_id'])
                    if run and run.get('cancelRequested'):
                        self._enqueue(db,device['id'],'CANCEL_ASSIGNMENT',{'assignmentId':assignment['id'],'epoch':assignment['epoch']},f'cancel-boot:{assignment["id"]}:{device["id"]}:{body.bootId}')
            for cid in body.acknowledgements:
                db.execute('UPDATE device_commands SET ack=1 WHERE id=? AND device_id=?',(cid,device['id']))
            for process in body.processes:
                if any(event.get('failure')=='RESTORE_MISMATCH' or event.get('reason')=='quarantined' for event in process.events):
                    db.execute('UPDATE devices SET status=?,enabled=0,desired=0 WHERE id=?',('QUARANTINED',device['id']))
                    self.store.cancel_selected(db,old['worker_id'])
                    for assignment in db.execute('SELECT a.run_id FROM assignments a JOIN device_reservations r ON a.id=r.assignment_id WHERE r.device_id=?',(device['id'],)).fetchall():
                        self.cancel(assignment['run_id'],db=db)
                    self.store.audit(db,'system','DEVICE_RESTORE_MISMATCH',device['id'])
            accepted_events=[]
            for event in body.events:
                assignment=db.execute('SELECT coordinator,epoch FROM assignments WHERE id=?',(event.assignmentId,)).fetchone()
                encoded=json.dumps(event.event,sort_keys=True,separators=(',',':'),allow_nan=False)
                expected=digest(event.assignmentId+encoded)
                if assignment and (assignment['coordinator'],assignment['epoch'])==(device['id'],event.epoch) and event.eventId==expected:
                    db.execute('INSERT OR IGNORE INTO monitoring_events(event_id,assignment_id,body) VALUES (?,?,?)',(event.eventId,event.assignmentId,encoded))
                    accepted_events.append(event.eventId)
            accepted=[]
            for report in body.reports:
                row=db.execute('SELECT * FROM assignments WHERE id=?',(report.assignmentId,)).fetchone()
                if not row or row['coordinator']!=device['id'] or row['epoch']!=report.epoch:continue
                if len(json.dumps(report.snapshot))>2_000_000:raise HTTPException(413,'Snapshot is too large')
                if report.snapshot.get('state',{}).get('status') not in QUIESCENT|{'STARTING','RUNNING','CANCELLING','RECOVERING','DRAINING','PAUSING'}:raise HTTPException(422,'Invalid runtime status')
                if report.snapshot['state']['status']=='PAUSED':
                    point=report.snapshot['state'].get('pauseCheckpoint',{})
                    import re
                    if point.get('verified') is not True or type(point.get('generation')) is not int or point['generation']<0 or not re.fullmatch('[a-f0-9]{32}',str(point.get('pointId',''))) or any(not re.fullmatch('[a-f0-9]{64}',str(point.get(k,''))) for k in ('childWeightsSha256','parentWeightsSha256')):
                        raise HTTPException(422,'Pause requires a verified completed checkpoint')
                if any(not isinstance(report.snapshot.get(k),list) for k in ('generations','candidates','attempts','events','artifacts')):raise HTTPException(422,'Invalid runtime snapshot')
                accepted.append({'assignmentId':report.assignmentId,'sequence':report.sequence})
                already=db.execute('SELECT 1 FROM device_reports WHERE device_id=? AND assignment_id=? AND sequence=?',(device['id'],report.assignmentId,report.sequence)).fetchone()
                if already:continue
                maximum=db.execute('SELECT max(sequence) FROM device_reports WHERE device_id=? AND assignment_id=?',(device['id'],report.assignmentId)).fetchone()[0] or 0
                db.execute('INSERT INTO device_reports VALUES (?,?,?)',(device['id'],report.assignmentId,report.sequence))
                if report.sequence>maximum and not row['released']:
                    db.execute('UPDATE assignments SET snapshot=? WHERE id=?',(json.dumps(report.snapshot,allow_nan=False),report.assignmentId))
                elif report.sequence>maximum and row['released']:
                    # A completed assignment can still finish artifact/event sync.
                    # Its terminal state and numerical lineage remain immutable.
                    cached=self.store.snapshot(row['run_id'])
                    latest=db.execute('SELECT id FROM assignments WHERE run_id=? ORDER BY epoch DESC LIMIT 1',(row['run_id'],)).fetchone()[0]
                    if latest==row['id'] and cached and 'artifactContents' in report.snapshot:
                        cached['artifactContents']=report.snapshot['artifactContents']
                        db.execute('UPDATE experiments SET snapshot=? WHERE id=?',(json.dumps(cached,allow_nan=False),row['run_id']))
            for row in db.execute('SELECT * FROM assignments WHERE released=0').fetchall():
                self._release_confirmed(db,row,json.loads(row['body']))
            old=db.execute('SELECT * FROM devices WHERE id=?',(device['id'],)).fetchone()
            allowed=old['status']=='APPROVED' and self.store.profile(old['owner'])['accountStatus']=='ACTIVE'
            commands=self.commands(device['id'])
            if not allowed:
                commands=[c for c in commands if c['kind'] in ('CANCEL_ASSIGNMENT','STOP_WORKER')]
            # Previously accepted assignments must remain recoverable even after OFF;
            # the agent adopts living processes but gates every new launch locally.
            return {'deviceId':device['id'],'approvalStatus':old['status'],'desiredContribution':bool(desired and allowed),
                    'commands':commands[:100], 'acceptedReports':accepted,'acceptedEvents':accepted_events,'heartbeatSeconds':10,'telemetrySupported':True,'detailedTelemetrySupported':True,
                    'releasedAssignments':[row['id'] for row in db.execute('SELECT id,body FROM assignments WHERE released=1') if device['id'] in json.loads(row['body'])['deviceIds']]}

    def worker_command(self, device, body):
        with self.store.db() as db:
            row,ar=self._assignment(db,body.assignmentId)
            if row['coordinator']!=device['id'] or row['epoch']!=body.epoch or body.workerId not in ar['workerDevices'] or row['released']:
                raise HTTPException(403,'Device is not authorized for this assignment')
            did=ar['workerDevices'][body.workerId]
            target=db.execute('SELECT * FROM devices WHERE id=?',(did,)).fetchone()
            reports=[p for p in json.loads(target['processes']) if p['assignmentId']==row['id'] and p['epoch']==row['epoch'] and p['recoveryIndex']==body.recoveryIndex]
            if body.action=='start':
                self._enqueue(db,did,'START_WORKER',{'assignmentId':row['id'],'epoch':row['epoch'],'runId':row['run_id'],
                    'workerId':body.workerId,'recoveryIndex':body.recoveryIndex,'coordinatorUrl':ar['computeUrl'],
                    'bulkUrl':ar.get('bulkUrl',ar['computeUrl']),
                    **({'studyConfig':ar['config']} if ar['config'].get('recipeVersion')==2 else {}),
                    'computeToken':ar['computeGrants'][body.workerId],
                    **({'publicComputeUrl':self.public_compute_url()} if self.public_compute_url() else {})},f'worker:{row["id"]}:{did}:{body.recoveryIndex}')
            elif body.action=='stop':
                self._enqueue(db,did,'STOP_WORKER',{'assignmentId':row['id'],'epoch':row['epoch'],'recoveryIndex':body.recoveryIndex},f'stop:{row["id"]}:{did}:{body.recoveryIndex}')
            if body.action in ('start','stop') and (time.time()-target['seen']>=30 or not reports):
                return {'alive':None,'ready':False,'events':[]}
            if time.time()-target['seen']>=30:raise HTTPException(503,'Worker process state is unknown')
            if body.action=='probe':
                if target['status']!='APPROVED' or not target['enabled'] or not target['desired']:raise HTTPException(409,'Worker contribution is OFF')
                return json.loads(target['self_test'])
            if not reports:raise HTTPException(503,'Waiting for worker acknowledgement')
            p=reports[0]
            return {'alive':p['workerAlive'],'ready':p['ready'],'events':p['events']}

    def maintenance(self):
        with self.store.db() as db:
            row=db.execute('SELECT value FROM settings WHERE key="agentMaintenance"').fetchone()
            return json.loads(row[0]) if row else None

    def acquire_maintenance(self):
        with self.store.db() as db:
            if self.reservations():raise RuntimeError('Confirmed GPU release is required')
            mid=uuid.uuid4().hex
            db.execute('INSERT OR REPLACE INTO settings VALUES (?,?)',('agentMaintenance',json.dumps({'maintenanceId':mid})))
            return {'maintenanceId':mid}

    def release_maintenance(self, maintenance_id):
        with self.store.db() as db:
            if (self.maintenance() or {}).get('maintenanceId')!=maintenance_id:raise ValueError('Wrong maintenance identity')
            db.execute('DELETE FROM settings WHERE key="agentMaintenance"')

    def artifact(self, run_id, name):
        import base64
        snapshot=self.store.snapshot(run_id)
        content=snapshot.get('artifactContents',{}).get(name)
        if content:
            data=base64.b64decode(content['base64'],validate=True)
            if hashlib.sha256(data).hexdigest()!=content['sha256']:raise HTTPException(409,'Cached artifact checksum mismatch')
            return iter([data])
        storage=getattr(self,'storage',None)
        if storage and re_checkpoint(name):
            for point in storage.points(run_id):
                if point['status']=='READY' and any(v['sha256']==name[:-4] for v in storage.manifest(point['pointId'])['files'].values()):
                    storage._requests(b=1)
                    return storage.backend.get('objects/'+name[:-4])
        raise HTTPException(409,'Artifact cloud sync is pending or the local source is unavailable')


def install_device_routes(app, store, user, runtime):
    def active(current):
        p=store.profile(current['userId'])
        if not p or p['accountStatus']!='ACTIVE':raise HTTPException(403,'Active account required')
        return p

    def admin(current=Depends(user)):
        p=active(current)
        if not p.get('platformAdmin'):raise HTTPException(403,'Platform administrator required')
        return p

    def device_auth(request:Request,authorization:str=Header(default='')):
        if not authorization.startswith('Bearer '):raise HTTPException(401,'Device authentication required')
        with store.db() as db:
            row=db.execute('SELECT * FROM devices WHERE token_digest=?',(digest(authorization[7:]),)).fetchone()
            if not row:raise HTTPException(401,'Device revoked or unknown')
            if row['status'] in ('REVOKED','QUARANTINED') or store.profile(row['owner'])['accountStatus']!='ACTIVE':
                drain=request.url.path=='/api/v1/device/poll'
                if request.url.path=='/api/v1/device/worker-command':
                    drain=bool(db.execute('SELECT 1 FROM assignments WHERE coordinator=? AND released=0',(row['id'],)).fetchone())
                if not drain:raise HTTPException(401,'Device revoked or unknown')
            return dict(row)

    @app.post('/api/v1/devices/pairing-codes')
    def pairing(current=Depends(user)):
        active(current);code=secrets.token_urlsafe(24)
        with store.db() as db:
            db.execute('INSERT INTO pairing_codes VALUES (?,?,?,0)',(digest(code),current['userId'],time.time()+600))
        return {'code':code,'expiresInSeconds':600}

    @app.post('/api/v1/device/enroll',status_code=201)
    def enroll(body:Enrollment):
        with store.db() as db:
            code=db.execute('SELECT * FROM pairing_codes WHERE digest=?',(digest(body.code),)).fetchone()
            if not code or code['used'] or code['expires']<=time.time():raise HTTPException(409,'Pairing code used or expired')
            if store.profile(code['owner'])['accountStatus']!='ACTIVE':raise HTTPException(403,'Owner access revoked')
            if db.execute('SELECT 1 FROM devices WHERE worker_id=?',(body.workerId,)).fetchone():raise HTTPException(409,'Worker alias already enrolled')
            legacy=db.execute('SELECT owner FROM worker_assignments WHERE worker_id=?',(body.workerId,)).fetchone()
            if legacy and legacy[0]!=code['owner']:raise HTTPException(403,'Worker alias belongs to another owner')
            did=uuid.uuid4().hex;token=secrets.token_urlsafe(32)
            db.execute('INSERT INTO devices(id,worker_id,owner,name,token_digest,status,compute_url,bulk_url,self_test) VALUES (?,?,?,?,?,?,?,?,?)',
                       (did,body.workerId,code['owner'],body.displayName,digest(token),'PENDING',body.computeUrl,body.bulkUrl,json.dumps(body.selfTest.model_dump())))
            db.execute('UPDATE pairing_codes SET used=1 WHERE digest=?',(digest(body.code),))
            db.execute('INSERT OR IGNORE INTO worker_assignments VALUES (?,?,NULL)',(body.workerId,code['owner']))
            store.audit(db,code['owner'],'DEVICE_ENROLLED',did)
            return {'deviceId':did,'workerId':body.workerId,'deviceToken':token,'approvalStatus':'PENDING'}

    @app.get('/api/v1/devices')
    def own_devices(current=Depends(user)):
        active(current)
        return [d for d in runtime.devices() if d['ownerUserId']==current['userId']]

    def update_endpoints(device_id, body, owner, boot_id=None):
        with store.db() as db:
            db.execute('BEGIN IMMEDIATE')
            d=db.execute('SELECT * FROM devices WHERE id=? AND owner=?',(device_id,owner)).fetchone()
            if not d:raise HTTPException(404,'Owned device not found')
            if boot_id is not None and d['boot_id']!=boot_id:raise HTTPException(409,'Current boot required')
            resource=json.loads(d['self_test']).get('gpuUUID')
            reserved=db.execute('SELECT 1 FROM device_reservations WHERE device_id=?',(device_id,)).fetchone()
            physical=db.execute('SELECT 1 FROM physical_reservations WHERE resource_id=?',(resource,)).fetchone()
            processes=json.loads(d['processes'])
            if (d['enabled'] or d['desired'] or reserved or physical or
                    any(p.get('coordinatorAlive') is not False or p.get('workerAlive') is not False for p in processes)):
                raise HTTPException(409,'Turn contribution OFF and confirm all processes drained before changing endpoints')
            db.execute('UPDATE devices SET compute_url=?,bulk_url=? WHERE id=?',(body.computeUrl,body.bulkUrl,device_id))
            store.audit(db,owner,'DEVICE_ENDPOINTS_CHANGED',device_id)
        return next(d for d in runtime.devices() if d['deviceId']==device_id)

    @app.patch('/api/v1/devices/{device_id}/endpoints')
    def owned_endpoints(device_id:str,body:EndpointUpdate,current=Depends(user)):
        return update_endpoints(device_id,body,active(current)['userId'])

    @app.patch('/api/v1/device/endpoints')
    def device_endpoints(body:DeviceEndpointUpdate,current=Depends(device_auth)):
        return update_endpoints(current['id'],body,current['owner'],body.bootId)

    @app.patch('/api/v1/device/qualification')
    def qualification(body:QualificationUpdate,current=Depends(device_auth)):
        with store.db() as db:
            db.execute('BEGIN IMMEDIATE')
            d=db.execute('SELECT * FROM devices WHERE id=?',(current['id'],)).fetchone()
            old=json.loads(d['self_test'])
            if (d['boot_id']!=body.bootId or d['enabled'] or d['desired'] or
                    db.execute('SELECT 1 FROM device_reservations WHERE device_id=?',(d['id'],)).fetchone() or
                    db.execute('SELECT 1 FROM physical_reservations WHERE resource_id=?',(old.get('gpuUUID'),)).fetchone()):
                raise HTTPException(409,'Current boot, OFF and confirmed drain required')
            if not body.selfTest.passed or body.selfTest.gpuUUID!=old.get('gpuUUID') or body.selfTest.platform!=old.get('platform','linux'):
                raise HTTPException(422,'Qualification cannot replace physical identity or platform')
            db.execute('UPDATE devices SET self_test=? WHERE id=?',(json.dumps(body.selfTest.model_dump()),d['id']))
            store.audit(db,d['owner'],'DEVICE_QUALIFICATION_UPDATED',d['id'])
        return {'updated':True}

    @app.get('/api/v1/platform/devices')
    def devices(current=Depends(admin)):
        return runtime.devices()

    @app.patch('/api/v1/platform/devices/{device_id}')
    def approve(device_id:str,body:Approval,current=Depends(admin)):
        with store.db() as db:
            d=db.execute('SELECT * FROM devices WHERE id=?',(device_id,)).fetchone()
            if not d:raise HTTPException(404,'Device not found')
            if body.approved:
                if d['status']=='QUARANTINED':raise HTTPException(409,'Restore mismatch quarantine requires investigation and fresh compatibility evidence')
                if d['status']=='REVOKED':raise HTTPException(409,'Re-enroll with a new device alias after revocation')
                if not json.loads(d['self_test'])['passed']:raise HTTPException(409,'Self-test must pass')
                if not body.workspaceId or not db.execute('SELECT 1 FROM memberships WHERE workspace_id=? AND user_id=?',(body.workspaceId,d['owner'])).fetchone():raise HTTPException(422,'Owner must belong to target workspace')
                if db.execute('SELECT 1 FROM device_reservations WHERE device_id=?',(device_id,)).fetchone():raise HTTPException(409,'Device is reserved')
                db.execute('UPDATE devices SET status="APPROVED" WHERE id=?',(device_id,))
                db.execute('UPDATE worker_assignments SET workspace_id=? WHERE worker_id=?',(body.workspaceId,d['worker_id']))
                disabled=store.disabled_workers(db);disabled.discard(d['worker_id'])
                db.execute('INSERT OR REPLACE INTO settings VALUES (?,?)',('disabledWorkers',json.dumps(sorted(disabled))))
            else:
                store.cancel_selected(db,d['worker_id'])
                for row in db.execute('SELECT a.run_id FROM assignments a JOIN device_reservations r ON a.id=r.assignment_id WHERE r.device_id=?',(device_id,)).fetchall():runtime.cancel(row[0],db=db)
                db.execute('UPDATE devices SET status="REVOKED",enabled=0,desired=0 WHERE id=?',(device_id,))
            store.audit(db,current['userId'],'DEVICE_APPROVAL' if body.approved else 'DEVICE_REVOKED',device_id,body.workspaceId)
        return next(d for d in runtime.devices() if d['deviceId']==device_id)

    @app.post('/api/v1/devices/{device_id}/contribution')
    def contribution(device_id:str,body:Contribution,current=Depends(user)):
        p=active(current)
        with store.db() as db:
            d=db.execute('SELECT * FROM devices WHERE id=? AND owner=?',(device_id,p['userId'])).fetchone()
            if not d:raise HTTPException(404,'Owned device not found')
            if d['status']!='APPROVED' or d['boot_id']!=body.bootId:raise HTTPException(409,'Approval and current boot identity required')
            db.execute('UPDATE devices SET desired=? WHERE id=?',(body.enabled,device_id))
            runtime._enqueue(db,device_id,'SET_CONTRIBUTION',{'enabled':body.enabled,'bootId':body.bootId},'contribution:'+uuid.uuid4().hex)
            if not body.enabled:
                store.cancel_selected(db,d['worker_id'])
                for row in db.execute('SELECT a.run_id FROM assignments a JOIN device_reservations r ON a.id=r.assignment_id WHERE r.device_id=?',(device_id,)).fetchall():runtime.cancel(row[0],db=db)
            store.audit(db,p['userId'],'DEVICE_ON' if body.enabled else 'DEVICE_OFF',device_id)
        return {'deviceId':device_id,'enabled':body.enabled,'pending':True}

    @app.post('/api/v1/device/poll')
    def poll(body:Poll,current=Depends(device_auth)):
        return runtime.poll(current,body)

    @app.post('/api/v1/device/worker-command')
    def worker(body:WorkerCommand,current=Depends(device_auth)):
        if (current['status'] in ('REVOKED','QUARANTINED') or store.profile(current['owner'])['accountStatus']!='ACTIVE') and body.action not in ('poll','stop'):
            raise HTTPException(401,'Revoked coordinators may only confirm or stop their existing workers')
        return runtime.worker_command(current,body)
    return device_auth
