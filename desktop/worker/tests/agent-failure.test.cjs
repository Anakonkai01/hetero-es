// What the owner sees when the local agent cannot run (the Windows r7 report): a specific code, a readable log, and a
// Start button that can try again. The agent is faked with `node` and a missing program, never with real Python.
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const os = require('node:os');
const path = require('node:path');
const { Bridge, classifyExit } = require('../electron/bridge.cjs');
const { createLog } = require('../electron/log.cjs');
const { Service } = require('../electron/service.cjs');

test('a program that cannot be started gives AGENT_SPAWN_FAILED with the system code kept for the log', async () => {
    const bridge = new Bridge(path.join(os.tmpdir(), 'no-such-dir', 'python.exe'), 'src', 'config.json', 'secret-device-token');
    await assert.rejects(bridge.ready, /^Error: AGENT_SPAWN_FAILED$/);
    assert.equal(bridge.failure().spawnCode, 'ENOENT');
    assert.equal(bridge.exited(), true);
});

test('an agent that exits early gives AGENT_EXITED; stderr is kept for the log but never in the error', async () => {
    // `node -m ...` is rejected by node itself: exit code 9 and a message on stderr, like a Python import error would be.
    const bridge = new Bridge(process.execPath, 'src', 'config.json', 'secret-device-token');
    await assert.rejects(bridge.ready, error => error.message === 'AGENT_EXITED');
    const failure = bridge.failure();
    assert.equal(failure.exitCode, 9);
    assert.match(failure.stderrTail, /bad option/);
    assert.equal(bridge.exited(), true);
    await assert.rejects(bridge.call('status'), /^Error: AGENT_EXITED$/);
});

test('missing Windows system libraries are recognised from the exit code or from the message', () => {
    assert.equal(classifyExit({ exitCode: 0xC0000135, stderrTail: '' }), 'WINDOWS_RUNTIME_MISSING');
    assert.equal(classifyExit({ exitCode: 0xC000007B, stderrTail: '' }), 'WINDOWS_RUNTIME_MISSING');
    assert.equal(classifyExit({ exitCode: 1, stderrTail: 'ImportError: DLL load failed while importing _ctypes' }), 'WINDOWS_RUNTIME_MISSING');
    assert.equal(classifyExit({ exitCode: 1, stderrTail: 'Traceback ...' }), 'AGENT_EXITED');
    assert.equal(classifyExit({ exitCode: null, signal: 'SIGKILL', stderrTail: '' }), 'AGENT_EXITED');
});

test('the log keeps multi-line detail, drops secrets and the user profile path, and is clipped', async t => {
    const dir = await fs.mkdtemp(path.join(os.tmpdir(), 'worker-log-'));
    t.after(() => fs.rm(dir, { recursive: true, force: true }));
    const log = createLog(dir, { home: 'C:\\Users\\Alice' });
    const secret = 'a'.repeat(40);
    log.detail('agent stderr', Array.from({ length: 40 }, (_, i) => 'line ' + i).join('\n') + `\nFile "C:\\Users\\Alice\\AppData\\x.py", line 3\nAuthorization: Bearer short-token\nsession ${secret}`);
    const text = log.tail();
    assert.ok(!text.includes('Alice'), 'user name must not be logged');
    assert.ok(!text.includes(secret), 'long token-like strings must not be logged');
    assert.ok(!text.includes('short-token'), 'a Bearer value must not be logged, however short');
    assert.match(text, /x\.py/);
    assert.ok(text.split('\n').length <= 22, 'detail is clipped to 20 lines');
    assert.ok(!text.includes('line 0\n'), 'only the end of the text is kept');
});

// A service whose agent cannot start. `failures` lets a test make the agent work again.
async function fixture(t, { failures = ['AGENT_EXITED'] } = {}) {
    const root = await fs.mkdtemp(path.join(os.tmpdir(), 'worker-failure-'));
    t.after(() => fs.rm(root, { recursive: true, force: true }));
    const logs = [];
    const log = { info: (message, fields) => logs.push({ message, ...fields }), detail: (message, text) => logs.push({ message, text }), error: () => { } };
    const state = { bootId: 'boot', enabled: false, drained: true, connection: { status: 'ONLINE' }, processes: [] };
    let starts = 0;
    const makeBridge = () => {
        const code = failures.shift();
        starts++;
        if (!code) return { ready: Promise.resolve(), call: async () => structuredClone(state), exited: () => false, failure: () => ({}) };
        const ready = Promise.reject(Error(code)); ready.catch(() => { });
        return {
            ready, call: async () => { throw Error(code); }, exited: () => true,
            failure: () => ({ code, exitCode: 1, spawnCode: '', stderrTail: 'ImportError: no module named heteroes\nAuthorization: Bearer ' + 'b'.repeat(40) }),
        };
    };
    const service = new Service(root, root, { available: () => true, read: async () => 'secret-device-token', write: async () => { } }, {
        log, makeBridge, setup: { running: false, status: () => ({ installed: true }), paths: () => ({ python: 'python', source: 'src', model: 'model' }) },
        fetch: async () => new Response(JSON.stringify({ agentMode: true })), now: () => clock.now,
    });
    const clock = { now: 1_000_000 };
    service.device = { deviceId: 'dev', workerId: 'desktop' };
    service.userToken = 'owner-session';
    service.settings.serverUrl = 'http://100.118.0.9:8002';
    return { service, logs, state, clock, starts: () => starts };
}

test('a dead agent is released, reported with its real code, and the Enable button is usable', async t => {
    const { service, logs } = await fixture(t);
    await assert.rejects(service.startAgent(), /^Error: AGENT_EXITED$/);
    assert.equal(service.bridge, null, 'a process that is known to be gone must not be kept as "ownership unknown"');
    const status = await service.status();
    assert.equal(status.agent.startError, 'AGENT_EXITED');
    assert.equal(status.agent.error, undefined, 'not an unknown process state');
    assert.equal(status.agent.drained, true);
    const entry = logs.find(row => row.message === 'agent failed');
    assert.equal(entry.code, 'AGENT_EXITED');
    assert.equal(entry.exitCode, 1);
    assert.equal(entry.lab, '100.118.0.9');
    const detail = logs.find(row => row.message === 'agent stderr');
    assert.match(detail.text, /no module named heteroes/);
});

test('the same failure is logged once even though the window polls every 3 seconds', async t => {
    const { service, logs, clock, starts } = await fixture(t, { failures: Array(10).fill('AGENT_EXITED') });
    for (let i = 0; i < 6; i++) { await service.status(); clock.now += 40_000; }
    assert.equal(logs.filter(row => row.message === 'agent failed').length, 1);
    assert.ok(starts() <= 6, 'one automatic retry per back-off window, not one per poll');
});

test('automatic retries wait 30 seconds between attempts', async t => {
    const { service, clock, starts } = await fixture(t, { failures: Array(10).fill('AGENT_EXITED') });
    await service.status();
    const first = starts();
    for (let i = 0; i < 5; i++) { clock.now += 3000; await service.status(); }
    assert.equal(starts(), first, 'polling every 3 s must not spawn a new agent each time');
    clock.now += 30_000; await service.status();
    assert.equal(starts(), first + 1);
});

test('pressing Enable after a failed start tries again and reports the real code, then works once the cause is gone', async t => {
    const { service, state } = await fixture(t, { failures: ['AGENT_EXITED', 'WINDOWS_RUNTIME_MISSING'] });
    await service.status();
    await assert.rejects(service.contribution(true), /^Error: WINDOWS_RUNTIME_MISSING$/);
    assert.equal((await service.status()).agent.startError, 'WINDOWS_RUNTIME_MISSING');
    let body; service.fetch = async (_url, options) => { body = JSON.parse(options.body); return new Response('{}'); };
    await service.contribution(true);
    assert.deepEqual(body, { enabled: true, bootId: 'boot' });
    const status = await service.status();
    assert.equal(status.agent.startError, undefined);
    assert.equal(state.enabled, false);
});

test('connection check says why the coordinator step cannot run when no agent is running', async t => {
    const { service } = await fixture(t);
    await service.status();
    const report = await service.checkConnection();
    const coordinator = report.checks.find(check => check.step === 'coordinator');
    assert.deepEqual({ status: coordinator.status, code: coordinator.code }, { status: 'FAIL', code: 'AGENT_EXITED' });
});

test('status never exposes the device token or stderr text', async t => {
    const { service } = await fixture(t);
    await service.status();
    const text = JSON.stringify(await service.status());
    assert.ok(!text.includes('secret-device-token') && !text.includes('no module named') && !text.includes('Bearer'));
});

test('an agent that dies after a good start is released and reported, not kept as an unknown process', async t => {
    const { service } = await fixture(t, { failures: [undefined] });
    await service.startAgent();
    assert.ok(service.bridge);
    let dead = false;
    service.bridge.call = async () => { if (dead) throw Error('AGENT_EXITED'); return { bootId: 'boot', enabled: false, drained: true, processes: [] }; };
    service.bridge.exited = () => dead;
    service.bridge.failure = () => ({ code: 'AGENT_EXITED', exitCode: 1, stderrTail: '' });
    assert.equal((await service.status()).agent.startError, undefined);
    dead = true;
    const status = await service.status();
    assert.equal(service.bridge, null);
    assert.equal(status.agent.startError, 'AGENT_EXITED');
    assert.equal(status.agent.error, undefined);
});
