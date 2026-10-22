const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const os = require('node:os');
const path = require('node:path');
const { Service, serverAddress } = require('../electron/service.cjs');
async function fixture(t) {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), 'worker-service-'));
  t.after(() => fs.rm(root, { recursive: true, force: true }));
  const calls = [];
  const state = { bootId: 'new-boot', enabled: false, drained: true, connection: { status: 'ONLINE' }, processes: [] };
  const bridge = {
    ready: Promise.resolve(),
    call: async (action) => {
      calls.push(action);
      if (action === 'off') state.enabled = false;
      return structuredClone(state);
    },
  };
  const service = new Service(
    root,
    root,
    { available: () => true, read: async () => 'secret-device-token', write: async () => {} },
    {
      setup: {
        running: false,
        status: () => ({ installed: true }),
        paths: () => ({ python: 'python', source: 'src', model: 'model' }),
      },
      makeBridge: () => bridge,
      fetch: async () => new Response(JSON.stringify({ agentMode: true })),
    },
  );
  return { service, bridge, state, calls, root };
}
test('HTTP is restricted to private networks; credentials and query are rejected', () => {
  assert.equal(serverAddress('http://100.92.20.58:8002/'), 'http://100.92.20.58:8002');
  for (const u of ['http://example.com', 'http://user:pass@localhost', 'https://example.com/?token=x', 'file:///tmp'])
    assert.throws(() => serverAddress(u));
});
test('a paired device can opt in without an account session and OFF stops locally', async (t) => {
  const { service, state, calls } = await fixture(t);
  service.device = { deviceId: 'dev', workerId: 'desktop' };
  await service.startAgent();
  service.settings.serverUrl = 'https://lab.example';
  const sent = [];
  service.fetch = async (url, options) => {
    sent.push([url, options.headers.Authorization, JSON.parse(options.body)]);
    return new Response('{}');
  };
  await service.contribution(true);
  assert.deepEqual(sent[0], [
    'https://lab.example/api/v1/device/contribution',
    'Bearer secret-device-token',
    { enabled: true },
  ]);
  state.enabled = true;
  await service.contribution(false);
  assert.equal(state.enabled, false);
  assert.ok(calls.includes('off'));
});
test('a legacy lab falls back to an owner session with the current boot only', async (t) => {
  const { service } = await fixture(t);
  service.device = { deviceId: 'dev', workerId: 'desktop' };
  await service.startAgent();
  service.userToken = 'owner-session';
  service.settings.serverUrl = 'https://lab.example';
  const sent = [];
  service.fetch = async (url, options) => {
    sent.push([url, options.headers.Authorization, JSON.parse(options.body)]);
    return new Response('{}', { status: url.endsWith('/device/contribution') ? 404 : 200 });
  };
  await service.contribution(true);
  assert.deepEqual(sent[1], [
    'https://lab.example/api/v1/devices/dev/contribution',
    'Bearer owner-session',
    { enabled: true, bootId: 'new-boot' },
  ]);
});
test('unknown process holds Quit; successful Quit is not restarted by polling', async (t) => {
  const { service, state } = await fixture(t);
  service.device = { deviceId: 'dev', workerId: 'desktop' };
  await service.startAgent();
  state.drained = false;
  assert.equal((await service.quit()).drained, false);
  assert.ok(service.bridge);
  state.drained = true;
  assert.equal((await service.quit()).drained, true);
  await service.status();
  assert.equal(service.bridge, null);
});
test('API outage still drains locally and public status never contains either token', async (t) => {
  const { service, state, calls } = await fixture(t);
  service.device = { deviceId: 'dev', workerId: 'desktop' };
  service.userToken = 'owner-session';
  await service.startAgent();
  service.fetch = async () => {
    throw Error('offline');
  };
  state.enabled = true;
  await service.quit();
  assert.ok(calls.includes('off'));
  const status = JSON.stringify(await service.status());
  assert.ok(!status.includes('owner-session') && !status.includes('secret-device-token'));
  const settings = await fs.readFile(path.join(service.root, 'agent-config.json'), 'utf8');
  assert.ok(!settings.includes('secret-device-token'));
});
test('URL rotation preserves enrolled identity only for the same server while drained OFF', async (t) => {
  const { service, state } = await fixture(t);
  service.device = { deviceId: 'dev', workerId: 'desktop' };
  service.settings.serverUrl = 'https://old.trycloudflare.com';
  service.settings.serverInstanceId = 'instance';
  service.fetch = async () => new Response(JSON.stringify({ agentMode: true, serverInstanceId: 'other' }));
  await assert.rejects(service.connect('https://new.trycloudflare.com'), /DIFFERENT_LAB/);
  assert.equal(service.settings.serverUrl, 'https://old.trycloudflare.com');
  service.fetch = async () => new Response(JSON.stringify({ agentMode: true, serverInstanceId: 'instance' }));
  await service.startAgent();
  state.enabled = true;
  await assert.rejects(service.connect('https://new.trycloudflare.com'), /STOP_WORK_FIRST/);
  state.enabled = false;
  await service.connect('https://new.trycloudflare.com');
  assert.equal(service.device.deviceId, 'dev');
  assert.equal(service.settings.serverUrl, 'https://new.trycloudflare.com');
  assert.equal(service.userToken, '');
  assert.equal(state.enabled, false);
});

test('requests identify themselves as HeteroES so a public edge does not block them', async (t) => {
  const { service } = await fixture(t);
  const seen = [];
  service.fetch = async (url, options) => {
    seen.push(options);
    return new Response(JSON.stringify({ agentMode: true, serverInstanceId: 'x' }));
  };
  service.settings.serverUrl = 'https://lab.example.org';
  await service.api('/api/v1/health');
  await service.connect('https://lab.example.org');
  assert.ok(seen.length >= 2);
  for (const options of seen) assert.match(options.headers?.['User-Agent'] ?? '', /^HeteroES-Worker\/\d/);
});

test('connection check preserves login, pairing and agent state; unassigned compute is explicitly untested', async (t) => {
  const { service, state } = await fixture(t);
  service.settings.serverUrl = 'https://lab.example.org';
  service.userToken = 'owner-session';
  service.session = { user: { displayName: 'Owner' } };
  service.fetch = async () => new Response(JSON.stringify({ ok: true, agentMode: true }));
  const report = await service.checkConnection();
  assert.equal(report.checks[0].status, 'PASS');
  assert.deepEqual(report.checks.slice(1), [
    { step: 'coordinator', status: 'SKIP', code: 'NO_ASSIGNMENT' },
    { step: 'bulk', status: 'SKIP', code: 'NO_ASSIGNMENT' },
  ]);
  assert.equal(service.userToken, 'owner-session');
  assert.equal(service.session.user.displayName, 'Owner');
  assert.equal(state.enabled, false);
  assert.equal(service.bridge, null);
  assert.ok(!JSON.stringify(report).includes('owner-session'));
});

test('connection failures report only safe codes, and compute reports come from the credential-owning bridge', async (t) => {
  const { service, bridge } = await fixture(t);
  service.settings.serverUrl = 'https://lab.example.org';
  service.fetch = async () => {
    throw Error('https://host/?token=private-secret');
  };
  let report = await service.checkConnection();
  assert.equal(report.checks[0].status, 'FAIL');
  assert.ok(!JSON.stringify(report).includes('private-secret'));
  service.fetch = async () => new Response(JSON.stringify({ ok: true, agentMode: true }));
  service.bridge = bridge;
  bridge.call = async (action) => {
    assert.equal(action, 'check_connection');
    return {
      assignments: [
        {
          assignmentId: 'a'.repeat(32),
          route: 'public',
          replayOnly: true,
          checks: [
            { step: 'coordinator', status: 'PASS', code: 'CONTROL_REACHABLE' },
            { step: 'bulk', status: 'SKIP', code: 'REPLAY_ONLY' },
          ],
        },
      ],
    };
  };
  report = await service.checkConnection();
  assert.equal(report.assignments[0].replayOnly, true);
  assert.equal(report.checks.length, 1);
});
test('opening with Windows is kept locally and keep ON after restart is the owner choice on the lab', async (t) => {
  const { service } = await fixture(t);
  assert.equal((await service.status()).startAtLogin, true); // the default: a restarted machine comes back
  assert.deepEqual(await service.preferences({ startAtLogin: false }), { startAtLogin: false, keepOn: false });
  assert.equal(JSON.parse(await fs.readFile(path.join(service.root, 'settings.json'), 'utf8')).startAtLogin, false);
  await assert.rejects(service.preferences({ keepOn: true }), /DEVICE_NOT_PAIRED/);
  service.device = { deviceId: 'dev', workerId: 'desktop' };
  await assert.rejects(service.preferences({ keepOn: true }), /SIGN_IN_REQUIRED/);
  service.userToken = 'owner-session';
  service.settings.serverUrl = 'https://lab.example';
  const sent = [];
  service.fetch = async (url, options) => {
    sent.push([url, options.method, JSON.parse(options.body)]);
    return new Response('{}');
  };
  service.settings.serverUrl = 'https://lab.example';
  assert.deepEqual(await service.preferences({ keepOn: true }), { startAtLogin: false, keepOn: true });
  assert.deepEqual(sent, [['https://lab.example/api/v1/devices/dev/contribution', 'PATCH', { keepAfterReboot: true }]]);
});
test('device policy failures are not retried with broader account credentials', async (t) => {
  const { service } = await fixture(t);
  service.device = { deviceId: 'dev', workerId: 'desktop' };
  await service.startAgent();
  service.userToken = 'owner-session';
  let requests = 0;
  service.fetch = async () => {
    requests++;
    return new Response('{}', { status: 403 });
  };
  await assert.rejects(service.contribution(true), /LAB_HTTP_403/);
  assert.equal(requests, 1);
});
test('signed out, status refreshes approval with the device token and keeps it for the next start', async (t) => {
  const { service } = await fixture(t);
  service.device = { deviceId: 'dev', workerId: 'desktop', displayName: 'old', approvalStatus: 'PENDING' };
  service.settings = { serverUrl: 'https://lab.example', device: service.device };
  await service.startAgent();
  const sent = [];
  service.fetch = async (url, options) => {
    sent.push([url, options.method, options.headers.Authorization]);
    return new Response(
      JSON.stringify({
        deviceId: 'dev',
        displayName: 'Thao',
        approvalStatus: 'APPROVED',
        deviceToken: 'leak',
        runs: [],
      }),
    );
  };
  const status = await service.status();
  assert.deepEqual(sent, [['https://lab.example/api/v1/device/summary', 'GET', 'Bearer secret-device-token']]);
  assert.equal(status.signedIn, false);
  assert.equal(status.device.approvalStatus, 'APPROVED');
  assert.equal(status.device.displayName, 'Thao');
  assert.ok(!JSON.stringify(status).includes('leak'));
  const saved = JSON.parse(await fs.readFile(path.join(service.root, 'settings.json'), 'utf8'));
  assert.equal(saved.device.approvalStatus, 'APPROVED');
  assert.ok(!JSON.stringify(saved).includes('leak') && !JSON.stringify(saved).includes('secret-device-token'));
});
test('signed out, a pending or rejected device stays blocked and an outage keeps the last known approval', async (t) => {
  const { service } = await fixture(t);
  service.device = { deviceId: 'dev', workerId: 'desktop', approvalStatus: 'APPROVED' };
  service.settings = { serverUrl: 'https://lab.example', device: service.device };
  await service.startAgent();
  service.fetch = async () => new Response(JSON.stringify({ deviceId: 'dev', approvalStatus: 'PENDING' }));
  assert.equal((await service.status()).device.approvalStatus, 'PENDING');
  service.device.approvalStatus = 'APPROVED';
  service.fetch = async () => {
    throw Error('offline');
  };
  assert.equal((await service.status()).device.approvalStatus, 'APPROVED');
  service.fetch = async () => new Response('{}', { status: 503 });
  assert.equal((await service.status()).device.approvalStatus, 'APPROVED');
  service.fetch = async () => new Response('{}', { status: 401 });
  assert.equal((await service.status()).device.approvalStatus, 'REVOKED');
});
test('signed in, the account device list is used and its approval is kept for the next start', async (t) => {
  const { service } = await fixture(t);
  service.device = { deviceId: 'dev', workerId: 'desktop', approvalStatus: 'PENDING' };
  service.settings = { serverUrl: 'https://lab.example', device: service.device };
  service.userToken = 'owner-session';
  await service.startAgent();
  const sent = [];
  service.fetch = async (url, options) => {
    sent.push([url, options.headers.Authorization]);
    return new Response(JSON.stringify([{ deviceId: 'dev', approvalStatus: 'APPROVED', lastSeen: 5 }]));
  };
  const status = await service.status();
  assert.equal(status.device.approvalStatus, 'APPROVED');
  assert.equal(status.device.lastSeen, 5);
  assert.deepEqual(sent, [['https://lab.example/api/v1/devices', 'Bearer owner-session']]);
  const saved = JSON.parse(await fs.readFile(path.join(service.root, 'settings.json'), 'utf8'));
  assert.equal(saved.device.approvalStatus, 'APPROVED');
  assert.equal(saved.device.lastSeen, undefined);
});
