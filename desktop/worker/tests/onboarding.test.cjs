// Lab-address entry, connection state and sign-out/sign-in behaviour of the Worker service (CPU only, no Electron).
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const os = require('node:os');
const path = require('node:path');
const { Service, serverAddress } = require('../electron/service.cjs');

async function fixture(t, options = {}) {
    const root = await fs.mkdtemp(path.join(os.tmpdir(), 'worker-onboarding-'));
    t.after(() => fs.rm(root, { recursive: true, force: true }));
    const state = { bootId: 'boot', enabled: false, drained: true, connection: { status: 'ONLINE' }, processes: [] };
    const bridge = { ready: Promise.resolve(), call: async action => { if (action === 'off') state.enabled = false; return structuredClone(state); } };
    let bridges = 0;
    const service = new Service(root, options.resources ?? root, { available: () => true, read: async () => 'device-token', write: async () => { } }, {
        setup: { running: false, status: () => ({ installed: true }), paths: () => ({ python: 'python', source: 'src', model: 'model' }) },
        makeBridge: () => { bridges++; return bridge; },
        fetch: options.fetch ?? (async () => new Response(JSON.stringify({ agentMode: true, serverInstanceId: 'lab' }))),
    });
    return { service, state, root, bridges: () => bridges };
}

test('a lab address can be typed or pasted the way people actually write it', () => {
    const accepted = {
        'lab.heteroes.site': 'https://lab.heteroes.site',
        '  https://lab.heteroes.site  ': 'https://lab.heteroes.site',
        'https://lab.heteroes.site/#downloads': 'https://lab.heteroes.site',
        'https://lab.heteroes.site/workspace': 'https://lab.heteroes.site',
        'HTTPS://Lab.HeteroES.site/': 'https://lab.heteroes.site',
        '100.92.20.58:8002': 'http://100.92.20.58:8002',
        'localhost:8002': 'http://localhost:8002',
        'http://192.168.1.5:8002/': 'http://192.168.1.5:8002',
    };
    for (const [typed, origin] of Object.entries(accepted)) assert.equal(serverAddress(typed), origin, typed);
});

test('an unusable lab address fails with a stable code, never a raw exception', () => {
    const rejected = {
        '': 'INVALID_LAB_ADDRESS', '   ': 'INVALID_LAB_ADDRESS', 'two words': 'INVALID_LAB_ADDRESS', 'https://': 'INVALID_LAB_ADDRESS',
        'https://exa mple.com': 'INVALID_LAB_ADDRESS', 'javascript:alert(1)': 'INVALID_LAB_ADDRESS', 'host:99999': 'INVALID_LAB_ADDRESS',
        'https://user:pass@lab.heteroes.site': 'INVALID_LAB_ADDRESS', 'https://lab.heteroes.site/?token=x': 'INVALID_LAB_ADDRESS',
        'http://lab.heteroes.site': 'HTTPS_OR_PRIVATE_NETWORK_REQUIRED', 'file:///tmp/x': 'HTTPS_OR_PRIVATE_NETWORK_REQUIRED',
        'ftp://lab.heteroes.site': 'HTTPS_OR_PRIVATE_NETWORK_REQUIRED',
    };
    for (const [typed, code] of Object.entries(rejected)) assert.throws(() => serverAddress(typed), error => error.message === code, `${JSON.stringify(typed)} -> ${code}`);
});

test('connect reports the connection as ONLINE and remembers the origin only', async t => {
    const seen = [];
    const { service } = await fixture(t, { fetch: async url => { seen.push(url); return new Response(JSON.stringify({ agentMode: true, serverInstanceId: 'lab', uiUrl: 'https://lab.heteroes.site' })); } });
    assert.equal((await service.status()).connection, 'OFFLINE');
    await service.connect('lab.heteroes.site/#downloads');
    assert.deepEqual(seen, ['https://lab.heteroes.site/api/v1/health']);
    assert.equal(service.settings.serverUrl, 'https://lab.heteroes.site');
    assert.equal((await service.status()).connection, 'ONLINE');
});

test('connect failures are told apart: unreachable, timeout, not a lab, server down, old lab', async t => {
    const cases = [
        ['LAB_UNREACHABLE', async () => { throw new TypeError('fetch failed'); }],
        ['LAB_TIMEOUT', async () => { throw new DOMException('This operation was aborted', 'AbortError'); }],
        ['NOT_A_LAB', async () => new Response('<html>hello</html>')],
        ['NOT_A_LAB', async () => new Response('[]')],
        ['LAB_HTTP_530', async () => new Response('error code: 1033', { status: 530 })],
        ['LAB_AGENT_MODE_REQUIRED', async () => new Response(JSON.stringify({ agentMode: false }))],
    ];
    for (const [code, fetch] of cases) {
        const { service } = await fixture(t, { fetch });
        await assert.rejects(service.connect('https://lab.heteroes.site'), error => error.message === code, code);
        assert.equal((await service.status()).connection, 'OFFLINE', code);
        assert.equal(service.settings.serverUrl, undefined, `${code} must not store the address`);
    }
});

test('Quit cancels a connection attempt that is still waiting instead of being blocked by it', async t => {
    const { service } = await fixture(t, { fetch: (_url, options) => new Promise((_resolve, reject) => options.signal.addEventListener('abort', () => reject(new DOMException('aborted', 'AbortError')))) });
    const attempt = service.connect('https://lab.heteroes.site');
    const outcome = assert.rejects(attempt, error => error.message === 'ACTION_CANCELLED');
    await new Promise(resolve => setImmediate(resolve));
    assert.deepEqual(await service.quit(), { drained: true });
    await outcome;
});

test('Quit does not abort a pairing request, which could lose the new device credential', async t => {
    let aborted = false;
    const { service } = await fixture(t, { fetch: (_url, options) => new Promise(resolve => { options.signal.addEventListener('abort', () => { aborted = true; }); setTimeout(() => resolve(new Response('{}')), 30); }) });
    service.settings.serverUrl = 'https://lab.heteroes.site';
    const pending = service.api('/api/v1/device/enroll', { code: 'x' }, '');
    await new Promise(resolve => setImmediate(resolve));
    await service.quit();
    await pending;
    assert.equal(aborted, false);
});

test('turning contribution OFF with nothing running succeeds', async t => {
    const { service } = await fixture(t);
    assert.deepEqual(await service.contribution(false), { enabled: false, drained: true });
    await assert.rejects(service.contribution(true), /AGENT_UNAVAILABLE/);
});

test('after Sign out the next Sign in brings the agent back, still with contribution OFF', async t => {
    const { service, bridges } = await fixture(t, { fetch: async url => new Response(JSON.stringify(String(url).endsWith('/auth/login') ? { accessToken: 'session', user: { displayName: 'Friend' } } : url.endsWith('/auth/logout') ? {} : { agentMode: true, serverInstanceId: 'lab', recipeVersions: [1] })) });
    service.settings.serverUrl = 'https://lab.heteroes.site';
    service.device = { deviceId: 'dev', workerId: 'desktop' };
    await service.login('friend', 'pw');
    await service.status();
    assert.equal(bridges(), 1);
    await service.logout();
    await service.status();
    assert.equal(bridges(), 1, 'signed out: the agent stays stopped');
    await service.login('friend', 'pw');
    await service.status();
    assert.equal(bridges(), 2, 'signed in again: the agent runs again');
    assert.equal(service.lastState.enabled, false);
});

test('the default lab address ships with the app and is offered until a lab is chosen', async t => {
    const resources = await fs.mkdtemp(path.join(os.tmpdir(), 'worker-defaults-'));
    t.after(() => fs.rm(resources, { recursive: true, force: true }));
    await fs.writeFile(path.join(resources, 'defaults.json'), JSON.stringify({ labUrl: 'https://lab.heteroes.site', build: 'r6' }));
    const { service } = await fixture(t, { resources });
    const status = await service.status();
    assert.equal(status.defaultLabUrl, 'https://lab.heteroes.site');
    assert.equal(status.build, 'r6');
    assert.equal(status.serverUrl, '');
    const { service: without } = await fixture(t);
    assert.equal((await without.status()).defaultLabUrl, '');
    await fs.writeFile(path.join(resources, 'defaults.json'), JSON.stringify({ labUrl: 'http://example.com' }));
    const { service: bad } = await fixture(t, { resources });
    assert.equal((await bad.status()).defaultLabUrl, '', 'an address the app would refuse is never offered');
});

test('a failed attempt at another address does not flip a working connection to OFFLINE; the same address does', async t => {
    let up = true;
    const { service } = await fixture(t, { fetch: async url => { if (String(url).includes('other.example')) throw new TypeError('fetch failed'); if (!up) throw new TypeError('fetch failed'); return new Response(JSON.stringify({ agentMode: true, serverInstanceId: 'lab' })); } });
    await service.connect('https://lab.heteroes.site');
    assert.equal((await service.status()).connection, 'ONLINE');
    await assert.rejects(service.connect('https://other.example'), /LAB_UNREACHABLE/);
    assert.equal((await service.status()).connection, 'ONLINE');
    up = false;
    await assert.rejects(service.connect('https://lab.heteroes.site'), /LAB_UNREACHABLE/);
    assert.equal((await service.status()).connection, 'OFFLINE');
});

test('Quit also cancels waiting reads such as the device list', async t => {
    const { service } = await fixture(t, { fetch: (_url, options) => new Promise((_resolve, reject) => options.signal.addEventListener('abort', () => reject(new DOMException('aborted', 'AbortError')))) });
    service.settings.serverUrl = 'https://lab.heteroes.site';
    const read = service.api('/api/v1/devices', undefined, 'token');
    const outcome = assert.rejects(read, error => error.message === 'ACTION_CANCELLED');
    await new Promise(resolve => setImmediate(resolve));
    await service.quit();
    await outcome;
});
