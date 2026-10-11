import pytest
from heteroes.product.agent import Agent
from heteroes.product.files import write_json,read_json


def agent(tmp_path):
    write_json(tmp_path/'config.json',{'serverUrl':'http://127.0.0.1:8002','deviceId':'a'*32,'workerId':'test',
        'deviceToken':'private','stateDirectory':str(tmp_path/'state'),'modelPath':'/model',
        'computeUrl':'http://127.0.0.1:8769','workerHost':'127.0.0.1','workerPort':8769})
    return Agent(tmp_path/'config.json')


def test_boot_resets_off_and_stale_enable_is_rejected(tmp_path):
    a=agent(tmp_path)
    a.handle({'commandId':'1','kind':'SET_CONTRIBUTION','bootId':a.boot_id,'enabled':True})
    assert a.enabled
    a.handle({'commandId':'2','kind':'SET_CONTRIBUTION','bootId':'old','enabled':True})
    b=Agent(tmp_path/'config.json')
    assert not b.enabled and b.boot_id!=a.boot_id


def test_shell_commands_and_bad_paths_never_execute(tmp_path):
    a=agent(tmp_path)
    for cmd in ({'commandId':'x','kind':'SHELL','argv':['touch','/tmp/unsafe']},
                {'commandId':'x','kind':'START_WORKER','runId':'../escape','assignmentId':'a'*32,'epoch':1}):
        with pytest.raises(ValueError):a.handle(cmd)


def test_coordinator_recovery_requires_explicit_on(tmp_path,monkeypatch):
    a=agent(tmp_path)
    root=a.manager.root/('b'*32);root.mkdir()
    write_json(root/'config.json',{'runId':'b'*32})
    write_json(root/'state.json',{'status':'RECOVERING'})
    launched=[];monkeypatch.setattr(a.manager,'_launch',lambda r:launched.append(r))
    a.manager.launch(root)
    assert launched==[]
    a.enabled=True;a.manager.launch(root)
    assert launched==[root]


def test_cancel_before_start_fences_delayed_worker_command(tmp_path,monkeypatch):
    a=agent(tmp_path);a.enabled=True
    cancel={'commandId':'cancel','kind':'CANCEL_ASSIGNMENT','assignmentId':'b'*32,'epoch':1}
    a.handle(cancel)
    started=[];monkeypatch.setattr(a,'_worker',lambda *args:started.append(args))
    a.handle({'commandId':'late-start','kind':'START_WORKER','assignmentId':'b'*32,'epoch':1,'runId':'c'*32})
    assert started==[]
    assert a.observe()[0]['workerAlive'] is False


def test_unknown_pid_birth_is_not_confirmed_dead():
    from heteroes.product.agent import owned_state
    assert owned_state({'pid':123,'birth':None}) is None
    assert owned_state(None,intent=True) is None


def test_duplicate_agent_does_not_change_current_boot(tmp_path):
    a=agent(tmp_path);a=Agent(tmp_path/'config.json',lock=True)
    before=read_json(a.root/'boot.json')
    with pytest.raises(BlockingIOError):Agent(tmp_path/'config.json',lock=True)
    assert read_json(a.root/'boot.json')==before
    a.instance_lock.close()


def test_monitoring_ack_is_durable_and_not_requeued(tmp_path,monkeypatch):
    a=agent(tmp_path);root=a.manager.root/('b'*32);root.mkdir()
    write_json(root/'assignment.json',{'assignmentId':'c'*32,'epoch':1})
    event={'event':'generation_done','generation':0,'t':1}
    snap={'state':{'status':'COMPLETED'},'events':[event],'artifacts':[],'generations':[],'candidates':[],'attempts':[]}
    monkeypatch.setattr(a.manager,'snapshot',lambda _:dict(snap))
    def reply(_,body):
        return {'approvalStatus':'APPROVED','desiredContribution':False,'commands':[],
            'acceptedReports':[{'assignmentId':'c'*32,'sequence':body['reports'][0]['sequence']}],
            'acceptedEvents':[e['eventId'] for e in body['events']]}
    monkeypatch.setattr(a,'call',reply)
    a.cycle();a.observe()
    with a.db() as db:assert db.execute('SELECT count(*) FROM event_outbox WHERE ack=0').fetchone()[0]==0


def test_large_monitoring_projection_preserves_completion_and_latest_metrics():
    import json
    from heteroes.product.agent import bounded_snapshot
    generations=[{'generationId':str(i),'status':'COMPLETED','committedCandidateCount':256,'modelVersion':'hash'} for i in range(1000)]
    snapshot={'state':{'status':'COMPLETED','finalWeightsSha256':'final-hash'},'generations':generations,
        'events':[{'data':'x'*10000} for _ in range(1000)],'candidates':[{'data':'y'*1000} for _ in range(2000)],
        'attempts':[{'data':'z'*1000} for _ in range(6000)],'artifactContents':{}}
    result=bounded_snapshot(snapshot)
    assert len(json.dumps(result).encode())<=1_250_000
    assert result['completedGenerationCount']==1000
    assert result['latestGeneration']==generations[-1]
    assert result['state']=={'status':'COMPLETED','finalWeightsSha256':'final-hash'}
    assert result['monitoringPartial']


def test_worker_only_observation_does_not_invent_unknown_coordinator(tmp_path,monkeypatch):
    a=agent(tmp_path)
    command={'assignmentId':'b'*32,'epoch':1,'recoveryIndex':0}
    directory=a.worker_directory(command)
    write_json(directory/'assignment.json',command)
    monkeypatch.setattr(a,'_worker',lambda *_:{'alive':False,'ready':False,'events':[]})
    state=a.observe()[0]
    assert state['coordinatorAlive'] is False and state['workerAlive'] is False


def test_desktop_profile_cannot_coordinate(tmp_path):
    a=agent(tmp_path);a.config['workerOnly']=True;a.enabled=True
    with pytest.raises(ValueError,match='worker-only'):
        a.handle({'commandId':'coordinate','kind':'COORDINATE'})


def test_desktop_quit_fences_late_enable_for_current_boot(tmp_path):
    a=agent(tmp_path);a.shutdown_requested=True
    with pytest.raises(RuntimeError,match='shutdown'):
        a.handle({'commandId':'late-enable','kind':'SET_CONTRIBUTION','bootId':a.boot_id,'enabled':True})
    assert not a.enabled


def test_released_assignment_never_launches_a_delayed_worker(tmp_path,monkeypatch):
    a=agent(tmp_path);a.enabled=True
    with a.db() as db:db.execute('INSERT INTO released VALUES (?)',('b'*32,))
    launched=[];monkeypatch.setattr(a,'_worker',lambda *args:launched.append(args))
    a.handle({'commandId':'old-start','kind':'START_WORKER','assignmentId':'b'*32,'epoch':1})
    assert launched==[]
    with a.db() as db:assert db.execute('SELECT 1 FROM processed WHERE id="old-start"').fetchone()


def test_resume_validates_checkpoint_preserves_ledger_and_rejects_old_epoch(tmp_path):
    import hashlib,sqlite3
    from heteroes.product.recovery import capture_point
    a=agent(tmp_path);a.enabled=True
    cfg={'runId':'b'*32,'workerIds':['test'],'workload':'arith16','decodeEngine':'hf_generate',
         'maxGenerations':3,'candidatesPerGeneration':4,'alpha':.001,'sigma':.001,
         'schedulerPolicy':'greedy','syncMode':'synchronous','backupPolicy':{'interval':1,'retain':3}}
    old={'assignmentId':'c'*32,'epoch':1,'config':cfg,'computeGrants':{'test':'old-private'}}
    a.manager.accept(old);root=a.manager.directory(cfg['runId'])
    (root/'weights').mkdir();payload=b'toy pause weights';sha=hashlib.sha256(payload).hexdigest()
    (root/'weights'/f'{sha}.bin').write_bytes(payload)
    with sqlite3.connect(root/'ledger.sqlite') as db:
        db.execute('CREATE TABLE generation_update(generation INTEGER,child_weights_sha256 TEXT,parent_weights_sha256 TEXT,applied_at REAL)')
        db.execute('INSERT INTO generation_update VALUES (0,?,?,1)',(sha,sha))
    summary={'generation':0,'child_sha256':sha,'parent_sha256':sha}
    point=capture_point(root,summary,{},cfg['backupPolicy'],final=True)
    paused={'pointId':point.name,'generation':0,'childWeightsSha256':sha,'parentWeightsSha256':sha,'verified':True}
    write_json(root/'pause-point.json',paused);(root/'pause.flag').touch()
    a.manager.save(root,status='PAUSED',workerStates={'test':{'alive':False,'confirmed':True}})
    ledger_before=(root/'ledger.sqlite').read_bytes()
    resumed={**old,'assignmentId':'d'*32,'epoch':2,'resumeFrom':paused,'computeGrants':{'test':'new-private'}}
    # Corrupt the independently retained checkpoint, then retry after restoring
    # it. A failed preflight leaves the old paused epoch intact.
    file=point/'weights'/f'{sha}.bin';file.write_bytes(b'corrupted')
    with pytest.raises(ValueError,match='checksum'):a.manager.accept(resumed)
    assert a.manager.state(root)['status']=='PAUSED'
    file.write_bytes(payload)
    a.manager.accept(resumed)
    assert a.manager.state(root)['status']=='STARTING'
    assert not (root/'pause.flag').exists()
    assert read_json(root/'assignment.json')['epoch']==2
    assert read_json(root/'device-grants.json')=={'test':'new-private'}
    assert (root/'ledger.sqlite').read_bytes()==ledger_before
    with pytest.raises(ValueError,match='epoch'):a.manager.accept(old)
