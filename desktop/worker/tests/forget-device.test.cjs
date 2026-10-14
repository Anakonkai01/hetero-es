// The owner was stuck on Windows: the app stayed paired to a Tailscale address that no longer answered, "Change lab"
// refused, and the only way out was deleting a folder by hand. "Forget this pairing" is the way out, and it must work
// with no network at all.
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const os = require('node:os');
const path = require('node:path');
const { Service } = require('../electron/service.cjs');

async function fixture(t, { fetch } = {}) {
    const root = await fs.mkdtemp(path.join(os.tmpdir(), 'worker-forget-'));
    t.after(() => fs.rm(root, { recursive: true, force: true }));
    const state = { bootId: 'boot', enabled: false, drained: true, connection: { status: 'ONLINE' }, processes: [] };
    const removed = [];
    const calls = [];
    const bridge = { ready: Promise.resolve(), exited: () => false, failure: () => ({}), call: async action => { calls.push(action); if (action === 'off') state.enabled = false; return structuredClone(state); } };
    const service = new Service(root, root, { available: () => true, read: async () => 'device-token', write: async () => { }, remove: async key => { removed.push(key); } }, {
        setup: { running: false, status: () => ({ installed: true }), paths: () => ({ python: 'python', source: 'src', model: 'model' }) },
        makeBridge: () => bridge,
        fetch: fetch ?? (async () => new Response(JSON.stringify({ agentMode: true, serverInstanceId: 'new-lab' }))),
    });
    service.settings.serverUrl = 'http://100.118.0.5:8002';
    service.settings.serverInstanceId = 'old-lab';
    service.settings.uiUrl = 'http://100.118.0.5:8002';
    service.device = { deviceId: 'dev', workerId: 'desktop-1', displayName: 'My PC' };
    service.settings.device = service.device;
    service.selfTest = { passed: true, platform: 'windows' };
    service.settings.selfTest = service.selfTest;
    service.userToken = 'owner-session';
    return { service, state, removed, calls, root };
}

test('Forget this pairing works with no network, removes the stored credential and unpairs', async t => {
    const { service, removed } = await fixture(t, { fetch: async () => { throw new TypeError('fetch failed', { cause: { code: 'ETIMEDOUT' } }); } });
    await service.startAgent();
    assert.deepEqual(await service.forgetDevice(), { ok: true });
    assert.deepEqual(removed, ['device-token']);
    assert.equal(service.device, null);
    assert.equal(service.bridge, null);
    assert.equal(service.userToken, '');
    const saved = JSON.parse(await fs.readFile(path.join(service.root, 'settings.json'), 'utf8'));
    assert.equal(saved.device, undefined);
    assert.equal(saved.serverUrl, undefined);
    assert.equal(saved.serverInstanceId, undefined);
    assert.ok(saved.selfTest.passed, 'the GPU compatibility result stays: it describes this computer, not the lab');
    const status = await service.status();
    assert.equal(status.device, null);
    assert.equal(status.serverUrl, '');
});

test('after forgetting, any lab can be connected, with no "different lab" refusal', async t => {
    const { service } = await fixture(t);
    await assert.rejects(service.connect('https://lab.example.org'), /DIFFERENT_LAB_REQUIRES_NEW_PAIRING/);
    await service.forgetDevice();
    await service.connect('https://lab.example.org');
    assert.equal(service.settings.serverUrl, 'https://lab.example.org');
    assert.equal(service.settings.serverInstanceId, 'new-lab');
});

test('Forget refuses while contribution is ON, so a running GPU job is never orphaned', async t => {
    const { service, state } = await fixture(t);
    await service.startAgent();
    state.enabled = true;
    await assert.rejects(service.forgetDevice(), /^Error: STOP_WORK_FIRST$/);
    assert.ok(service.device, 'the pairing is kept');
});

test('Forget refuses when a process has not confirmed it stopped', async t => {
    const { service, state } = await fixture(t);
    await service.startAgent();
    state.drained = false;
    await assert.rejects(service.forgetDevice(), /^Error: STOP_WORK_FIRST$|^Error: DRAIN_NOT_CONFIRMED$/);
    assert.ok(service.device);
});

test('the old agent state is set aside, not deleted, and a new pairing starts empty', async t => {
    const { service, root } = await fixture(t);
    await fs.mkdir(path.join(root, 'agent-state'));
    await fs.writeFile(path.join(root, 'agent-state', 'boot.json'), '{}');
    await service.forgetDevice();
    const names = await fs.readdir(root);
    assert.ok(!names.includes('agent-state'));
    assert.ok(names.some(name => name.startsWith('agent-state.forgotten-')));
});

test('Change lab while paired and the old address is dead says so, instead of a bare timeout', async t => {
    let calls = 0;
    const { service } = await fixture(t, { fetch: async url => { calls++; if (String(url).startsWith('http://100.118')) throw new TypeError('fetch failed', { cause: { code: 'UND_ERR_CONNECT_TIMEOUT' } }); return new Response(JSON.stringify({ agentMode: true, serverInstanceId: 'new-lab' })); } });
    delete service.settings.serverInstanceId;
    await assert.rejects(service.connect('https://lab.heteroes.site'), /^Error: OLD_LAB_UNREACHABLE$/);
    assert.ok(service.device, 'nothing is changed by a failed attempt');
    assert.equal(service.settings.serverUrl, 'http://100.118.0.5:8002');
});

test('forgetting is not offered to a computer that is not paired', async t => {
    const { service } = await fixture(t);
    service.device = null; delete service.settings.device;
    assert.deepEqual(await service.forgetDevice(), { ok: true });
});
