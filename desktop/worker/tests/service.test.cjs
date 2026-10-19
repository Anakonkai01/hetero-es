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
test('owner opt-in is boot scoped and OFF stops locally even without a session', async (t) => {
  const { service, state, calls } = await fixture(t);
  service.device = { deviceId: 'dev', workerId: 'desktop' };
  await service.startAgent();
  await assert.rejects(service.contribution(true), /SIGN_IN/);
  state.enabled = true;
  await service.contribution(false);
  assert.equal(state.enabled, false);
  assert.ok(calls.includes('off'));
  let body;
  service.userToken = 'owner-session';
  service.fetch = async (_url, options) => {
    body = JSON.parse(options.body);
    return new Response('{}');
  };
  await service.contribution(true);
  assert.deepEqual(body, { enabled: true, bootId: 'new-boot' });
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
