"""Holding admission must not stall current ownership or lifecycle reports."""
import json
from labkit import boot, enable, pair, queued
from test_pause_resume import paused_report, stopped


def hold(store, value=True):
    with store.db() as db:db.execute('UPDATE settings SET value=? WHERE key="dispatchHold"',(json.dumps(value),))


def test_held_queue_stays_queued_without_creating_an_assignment(lab):
    _, store, runtime, _ = lab
    device, auth=pair(lab);enable(lab,device,auth)
    run=queued(lab,device);hold(store)
    store.dispatch_once()
    assert store.get(run)['status']=='QUEUED'
    assert runtime.runs()==[] and runtime.reservations()==[]
    hold(store,False);store.dispatch_once()
    assert store.get(run)['status']=='STARTING' and len(runtime.runs())==1


def test_held_queue_still_reconciles_completion_and_releases_only_on_drain(lab):
    client,store,runtime,_=lab
    device,auth=pair(lab);enable(lab,device,auth)
    run=queued(lab,device);store.dispatch_once();assignment=runtime.runs()[0]
    hold(store)
    report={'assignmentId':assignment['assignmentId'],'epoch':assignment['epoch'],'sequence':1,
        'snapshot':{'state':{'status':'COMPLETED'},'generations':[],'candidates':[],'attempts':[],
                    'events':[],'artifacts':[],'completedGenerationCount':3}}
    boot(client,auth,'boot-1',contribution=True,reports=[report])
    store.dispatch_once()
    assert store.get(run)['status']=='DRAINING' and runtime.reservations()
    boot(client,auth,'boot-1',contribution=True,processes=[stopped(assignment)])
    store.dispatch_once()
    assert store.get(run)['status']=='COMPLETED' and store.get(run)['completedGenerations']==3
    assert runtime.reservations()==[]


def test_held_queue_still_forwards_durable_cancel_after_a_lost_request(lab):
    _,store,runtime,_=lab
    device,auth=pair(lab);enable(lab,device,auth)
    run=queued(lab,device);store.dispatch_once()
    with store.db() as db:
        body=store.get(run);body.update(cancelRequested=True,status='CANCELLING');store.save(db,body)
    hold(store);store.dispatch_once()
    assert any(c['kind']=='CANCEL_ASSIGNMENT' for c in runtime.commands(device['deviceId']))
    assert runtime.reservations()  # A command is not evidence that a process stopped.


def test_held_queue_still_reconciles_pause(lab):
    client,store,runtime,owner=lab
    device,auth=pair(lab);enable(lab,device,auth)
    run=queued(lab,device);store.dispatch_once();assignment=runtime.runs()[0]
    hold(store)
    assert client.post(f'/api/v1/experiments/{run}/pause',headers=owner).status_code==200
    boot(client,auth,'boot-1',contribution=True,reports=[paused_report(assignment)],processes=[stopped(assignment)])
    store.dispatch_once()
    assert store.get(run)['status']=='PAUSED' and runtime.reservations()==[]


def test_hold_during_reconcile_blocks_new_admission_in_the_same_tick(lab,monkeypatch):
    _,store,runtime,_=lab
    first,h1=pair(lab,'first');second,h2=pair(lab,'second')
    enable(lab,first,h1);enable(lab,second,h2)
    one=queued(lab,first);store.dispatch_once()
    two=queued(lab,second)
    original=store._dispatch_run
    def reconcile(body):
        original(body)
        if body['experimentId']==one:hold(store)
    monkeypatch.setattr(store,'_dispatch_run',reconcile)
    store.dispatch_once()
    assert store.get(two)['status']=='QUEUED' and len(runtime.runs())==1


def test_reconcile_errors_are_reported_while_held_and_do_not_skip_other_runs(lab,monkeypatch):
    _,store,runtime,_=lab
    first,h1=pair(lab,'first');second,h2=pair(lab,'second')
    enable(lab,first,h1);enable(lab,second,h2)
    one=queued(lab,first);two=queued(lab,second);store.dispatch_once();hold(store)
    calls=[]
    def reconcile(body):
        calls.append(body['experimentId'])
        if body['experimentId']==one:raise ConnectionError('offline')
    monkeypatch.setattr(store,'_dispatch_run',reconcile)
    store.dispatch_once()
    assert calls==[one,two]
    assert store.last_error=='ConnectionError'
