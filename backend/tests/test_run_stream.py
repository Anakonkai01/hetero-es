"""The timeline endpoint and the live stream behind the Live screen."""
import asyncio
import json
import time
from pathlib import Path

from labkit import draft, login

FIXTURE = json.loads((Path(__file__).parent / 'fixtures' / 'run-fifo.json').read_text())


def seeded_run(client, store, headers, status='COMPLETED', snapshot=None):
    """A run owned by the admin whose stored body and snapshot come from a real recorded run."""
    created = draft(client, headers).json()
    body = {**FIXTURE['body'], 'experimentId': created['experimentId'], 'ownerUserId': created['ownerUserId'], 'workspaceId': created['workspaceId'], 'status': status}
    with store.db() as db:
        db.execute('UPDATE experiments SET body=?, snapshot=? WHERE id=?', (json.dumps(body), json.dumps(snapshot or FIXTURE['snapshot']), created['experimentId']))
    return created['experimentId']


def parse(chunk):
    """('timeline', {...}) / ('end', {...}) / ('comment', ': heartbeat') from one SSE chunk."""
    lines = chunk.strip().split('\n')
    if lines[0].startswith(':'):
        return 'comment', lines[0]
    return lines[0][6:].strip(), json.loads(lines[1][5:])


async def collect(live, store, run, until, timeout=10):
    """Read frames straight from the generator (TestClient cannot hold an endless stream open)."""
    assert live.acquire()
    chunks = []
    frames = live.frames(store, run)
    try:
        async with asyncio.timeout(timeout):
            async for chunk in frames:
                chunks.append(parse(chunk))
                if until(chunks):
                    break
    finally:
        await frames.aclose()
    return chunks


def test_the_timeline_endpoint_describes_a_recorded_run(setup):
    client, store, _ = setup
    headers = login(client, 'admin')
    run = seeded_run(client, store, headers)
    reply = client.get(f'/api/v1/experiments/{run}/timeline', headers=headers)
    assert reply.status_code == 200
    timeline = reply.json()
    assert timeline['experiment']['id'] == run and len(timeline['jobs']) == 2 and timeline['nowMs'] > 0
    assert client.get(f'/api/v1/experiments/{run}/timeline').status_code == 401
    assert client.get('/api/v1/experiments/unknown/timeline', headers=headers).status_code == 404


def test_a_member_of_another_workspace_cannot_see_the_timeline_or_the_stream(setup):
    client, store, _ = setup
    admin = login(client, 'admin')
    run = seeded_run(client, store, admin)
    outsider = login(client, 'participant')
    assert client.get(f'/api/v1/experiments/{run}/timeline', headers=outsider).status_code == 404
    assert client.get(f'/api/v1/experiments/{run}/stream', headers=outsider).status_code == 404


def test_a_finished_run_streams_once_and_ends_over_http(setup):
    client, store, _ = setup
    headers = login(client, 'admin')
    run = seeded_run(client, store, headers)
    reply = client.get(f'/api/v1/experiments/{run}/stream', headers=headers)
    assert reply.status_code == 200 and reply.headers['content-type'].startswith('text/event-stream')
    assert reply.headers['cache-control'].startswith('no-cache') and reply.headers['x-accel-buffering'] == 'no'
    kinds = [parse(chunk)[0] for chunk in reply.text.strip().split('\n\n')]
    assert kinds == ['timeline', 'end']
    assert len(parse(reply.text.strip().split('\n\n')[0])[1]['jobs']) == 2
    assert client.app.state.live.active == 0


def test_a_running_run_pushes_changes_and_heartbeats_but_never_repeats_itself(setup):
    client, store, _ = setup
    live = client.app.state.live
    live.poll, live.heartbeat = 0.05, 0.2
    headers = login(client, 'admin')
    snapshot = json.loads(json.dumps(FIXTURE['snapshot']))
    snapshot['state']['status'] = 'RUNNING'
    run = seeded_run(client, store, headers, status='RUNNING', snapshot=snapshot)

    async def scenario():
        def change():
            changed = json.loads(json.dumps(snapshot))
            changed['attempts'][0]['status'] = 'FAILED'
            with store.db() as db:
                db.execute('UPDATE experiments SET snapshot=? WHERE id=?', (json.dumps(changed), run))
        asyncio.get_running_loop().call_later(0.6, change)
        return await collect(live, store, run, until=lambda items: sum(kind == 'timeline' for kind, _ in items) >= 2)

    items = asyncio.run(scenario())
    kinds = [kind for kind, _ in items]
    assert kinds.count('timeline') == 2 and kinds.count('comment') >= 1 and kinds[0] == 'timeline', kinds
    first, second = [data for kind, data in items if kind == 'timeline']
    assert first['jobs'][0]['status'] == 'SUCCEEDED' and second['jobs'][0]['status'] == 'FAILED'
    assert live.active == 0, 'leaving frees the slot'


def test_a_run_that_finishes_while_watched_ends_the_stream(setup):
    client, store, _ = setup
    live = client.app.state.live
    live.poll = 0.05
    headers = login(client, 'admin')
    run = seeded_run(client, store, headers, status='RUNNING')

    async def scenario():
        def finish():
            with store.db() as db:
                body = json.loads(db.execute('SELECT body FROM experiments WHERE id=?', (run,)).fetchone()[0])
                db.execute('UPDATE experiments SET body=? WHERE id=?', (json.dumps({**body, 'status': 'COMPLETED'}), run))
        asyncio.get_running_loop().call_later(0.3, finish)
        return await collect(live, store, run, until=lambda items: items[-1][0] == 'end')

    assert [kind for kind, _ in asyncio.run(scenario())][-1] == 'end'


def test_too_many_viewers_are_refused_and_the_slot_is_freed_when_one_leaves(setup):
    client, store, _ = setup
    live = client.app.state.live
    live.limit = 1
    headers = login(client, 'admin')
    run = seeded_run(client, store, headers)
    assert live.acquire()
    refused = client.get(f'/api/v1/experiments/{run}/stream', headers=headers)
    assert refused.status_code == 429 and 'Too many' in refused.json()['message']
    live.release()
    assert client.get(f'/api/v1/experiments/{run}/stream', headers=headers).status_code == 200
    assert live.active == 0


def test_a_stream_that_runs_too_long_is_ended_politely(setup):
    client, store, _ = setup
    live = client.app.state.live
    live.poll, live.max_seconds = 0.05, 0.2
    headers = login(client, 'admin')
    snapshot = json.loads(json.dumps(FIXTURE['snapshot']))
    run = seeded_run(client, store, headers, status='RUNNING', snapshot=snapshot)
    items = asyncio.run(collect(live, store, run, until=lambda items: items[-1][0] == 'end'))
    assert items[-1][0] == 'end'
