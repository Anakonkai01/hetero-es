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
