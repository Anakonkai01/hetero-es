const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const os = require('node:os');
const path = require('node:path');
const { Service } = require('../electron/service.cjs');

async function fixture(t, platform = 'linux') {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), 'worker-compute-'));
  t.after(() => fs.rm(root, { recursive: true, force: true }));
  const requests = [],
    configs = [];
  const state = { bootId: 'boot', enabled: false, drained: true, processes: [] };
  const service = new Service(
    root,
    root,
    { available: () => true, read: async () => 'device-secret' },
    {
      platform,
      interfaces: () => ({
        eth0: [{ family: 'IPv4', address: '192.168.1.8', internal: false }],
        tailscale0: [{ family: 'IPv4', address: '100.92.20.58', internal: false }],
        public: [{ family: 'IPv4', address: '8.8.8.8', internal: false }],
      }),
      setup: {
        running: false,
        status: () => ({ installed: true }),
        paths: () => ({ python: 'python', source: 'src', model: 'model' }),
      },
      makeBridge: (_python, _source, config) => {
        configs.push(JSON.parse(require('node:fs').readFileSync(config, 'utf8')));
        return { ready: Promise.resolve(), call: async () => structuredClone(state) };
      },
      fetch: async (url, options) => {
        requests.push({ url, body: options.body && JSON.parse(options.body) });
        return new Response(JSON.stringify({ ok: true, agentMode: true, deviceConfiguration: true }));
      },
    },
  );
  service.settings.serverUrl = 'https://lab.example.org';
  service.selfTest = { passed: true, coordinator: true, platform, vramTotalMb: 16000, recipeVersions: [1] };
  return { service, root, requests, configs, state };
}

test('qualified Linux coordinator advertises and binds the chosen local address, persists across restart, boots OFF', async (t) => {
  const { service, root, configs } = await fixture(t);
  await service.configureCompute({ network: 'overlay', coordinator: true, host: '100.92.20.58' });
  service.device = { deviceId: 'dev', workerId: 'desktop' };
  await service.startAgent();
  assert.equal(configs[0].workerOnly, false);
  assert.equal(configs[0].workerHost, '100.92.20.58');
  assert.equal(configs[0].computeUrl, 'http://100.92.20.58:8765');
  assert.equal(configs[0].selfTest.coordinator, true);
  assert.equal((await service.status()).agent.enabled, false);
  assert.equal(JSON.parse(await fs.readFile(path.join(root, 'settings.json'))).compute.coordinator, true);
  assert.ok(!(await fs.readFile(path.join(root, 'agent-config.json'), 'utf8')).includes('device-secret'));
});

test('coordinator capability requires the passed self-test of this machine and reported capability', async (t) => {
  for (const changes of [{ passed: false }, { coordinator: false }, { platform: 'windows' }]) {
    const { service } = await fixture(t);
    Object.assign(service.selfTest, changes);
    await assert.rejects(
      service.configureCompute({ network: 'lan', coordinator: true, host: '192.168.1.8' }),
      /COORDINATOR_NOT_QUALIFIED/,
    );
  }
  const { service } = await fixture(t, 'win32');
  service.selfTest.platform = 'linux'; // a self-test from another machine
  await assert.rejects(
    service.configureCompute({ network: 'lan', coordinator: true, host: '192.168.1.8' }),
    /COORDINATOR_NOT_QUALIFIED/,
  );
});

test('a Windows machine and a small GPU may coordinate (owner 2026-10-20)', async (t) => {
  const { service } = await fixture(t, 'win32');
  Object.assign(service.selfTest, { platform: 'windows', vramTotalMb: 6144 });
  await service.configureCompute({ network: 'lan', coordinator: true, host: '192.168.1.8' });
});

test('listen address must belong to this computer and fit the chosen network', async (t) => {
  const { service } = await fixture(t);
  for (const host of ['127.0.0.1', '0.0.0.0', '8.8.8.8', '192.168.1.99', 'https://host', '100.92.20.58']) {
    await assert.rejects(
      service.configureCompute({ network: 'lan', coordinator: true, host }),
      /INVALID_COMPUTE_ADDRESS/,
    );
  }
  await assert.rejects(service.configureCompute({ network: 'unknown', coordinator: false }), /INVALID_NETWORK/);
  assert.deepEqual(
    (await service.status()).compute.addresses.map((a) => a.host),
    ['192.168.1.8', '100.92.20.58'],
  );
});

test('existing worker changes endpoints and role together only while signed in, OFF and drained', async (t) => {
  const { service, requests, configs, state } = await fixture(t);
  service.device = { deviceId: 'dev', workerId: 'desktop' };
  await service.startAgent();
  const desired = { network: 'lan', coordinator: true, host: '192.168.1.8' };
  await assert.rejects(service.configureCompute(desired), /SIGN_IN_REQUIRED/);
  service.userToken = 'owner';
  state.enabled = true;
  await assert.rejects(service.configureCompute(desired), /STOP_WORK_FIRST/);
  state.enabled = false;
  state.drained = false;
  await assert.rejects(service.configureCompute(desired), /STOP_WORK_FIRST/);
  state.drained = true;
  await service.configureCompute(desired);
  const update = requests.find((r) => r.url.endsWith('/api/v1/devices/dev/configuration'));
  assert.equal(update.body.computeUrl, 'http://192.168.1.8:8765');
  assert.equal(update.body.selfTest.coordinator, true);
  assert.equal(configs.at(-1).workerOnly, false);
  assert.equal(state.enabled, false);
});

test('rejected server update preserves the old worker settings and restarts it OFF', async (t) => {
  const { service, configs } = await fixture(t);
  service.device = { deviceId: 'dev', workerId: 'desktop' };
  service.userToken = 'owner';
  await service.startAgent();
  service.fetch = async (url) =>
    new Response(JSON.stringify({ deviceConfiguration: true }), { status: url.endsWith('/configuration') ? 409 : 200 });
  await assert.rejects(
    service.configureCompute({ network: 'lan', coordinator: true, host: '192.168.1.8' }),
    /LAB_HTTP_409/,
  );
  assert.equal(service.settings.compute, undefined);
  assert.equal(configs.at(-1).workerOnly, true);
  assert.ok(service.bridge);
});

test('worker role stays loopback; disappearing or no-longer-qualified coordinator settings cannot start an agent', async (t) => {
  const { service, configs } = await fixture(t);
  service.device = { deviceId: 'dev', workerId: 'desktop' };
  service.userToken = 'owner';
  await service.configureCompute({ network: 'internet', coordinator: false });
  assert.equal(configs.at(-1).workerOnly, true);
  assert.equal(configs.at(-1).workerHost, '127.0.0.1');
  assert.equal(configs.at(-1).selfTest.coordinator, false);
  await service.quit();
  service.settings.compute = { network: 'lan', coordinator: true, host: '192.168.1.99' };
  await assert.rejects(service.startAgent(), /INVALID_COMPUTE_ADDRESS/);
  service.settings.compute.host = '192.168.1.8';
  service.selfTest.passed = false;
  await assert.rejects(service.startAgent(), /COORDINATOR_NOT_QUALIFIED/);
});

test('lost configuration reply records uncertainty and prevents polling from silently restarting the old role', async (t) => {
  const { service, root, configs } = await fixture(t);
  service.device = { deviceId: 'dev', workerId: 'desktop' };
  service.userToken = 'owner';
  await service.startAgent();
  service.fetch = async (url) => {
    if (url.endsWith('/configuration')) throw Error('reply lost');
    return new Response(JSON.stringify({ deviceConfiguration: true }));
  };
  await assert.rejects(service.configureCompute({ network: 'lan', coordinator: true, host: '192.168.1.8' }));
  assert.ok(JSON.parse(await fs.readFile(path.join(root, 'settings.json'))).computePending);
  await assert.rejects(service.startAgent(), /COMPUTE_CHANGE_PENDING/);
  await service.status();
  assert.equal(service.bridge, null);
  assert.equal(configs.length, 1);
  service.fetch = async () => new Response(JSON.stringify({ deviceConfiguration: true }));
  await service.configureCompute({ network: 'lan', coordinator: true, host: '192.168.1.8' });
  assert.equal(service.settings.computePending, undefined);
  assert.equal(configs.at(-1).workerOnly, false);
});

test('cannot change server configuration if the local pending record cannot be saved', async (t) => {
  const { service, requests } = await fixture(t);
  service.device = { deviceId: 'dev', workerId: 'desktop' };
  service.userToken = 'owner';
  await service.startAgent();
  service.save = async () => {
    throw Error('disk full');
  };
  await assert.rejects(
    service.configureCompute({ network: 'lan', coordinator: true, host: '192.168.1.8' }),
    /disk full/,
  );
  assert.ok(!requests.some((r) => r.url.endsWith('/configuration')));
  assert.equal(service.settings.compute, undefined);
  assert.equal(service.settings.computePending, undefined);
});

test('startup qualification failure keeps an uncertain bridge owned until Quit confirms drain', async (t) => {
  const { service, state } = await fixture(t);
  service.device = { deviceId: 'dev', workerId: 'desktop' };
  service.selfTest.recipeVersions = [1, 2];
  state.drained = false;
  service.fetch = async (url) =>
    new Response(JSON.stringify({ recipeVersions: [1, 2] }), { status: url.endsWith('/qualification') ? 403 : 200 });
  await assert.rejects(service.startAgent(), /LAB_HTTP_403/);
  assert.ok(service.bridge);
  state.drained = true;
  assert.equal((await service.quit()).drained, true);
  assert.equal(service.bridge, null);
});

test('a v3 device sends its qualification only to a lab that speaks v3', async (t) => {
  for (const [device, lab, sent] of [
    [[3], [1, 2, 3], true],
    [[3], [1, 2], false],
    [[1, 2], [1, 2], true],
    [[1], [1, 2, 3], false],
  ]) {
    const { service, requests } = await fixture(t);
    service.device = { deviceId: 'dev', workerId: 'desktop' };
    service.selfTest.recipeVersions = device;
    service.fetch = async (url, options) => {
      requests.push({ url, body: options.body && JSON.parse(options.body) });
      return new Response(JSON.stringify({ ok: true, recipeVersions: lab }));
    };
    await service.startAgent();
    const patch = requests.find((r) => r.url.endsWith('/device/qualification'));
    assert.equal(Boolean(patch), sent, JSON.stringify({ device, lab }));
    if (sent) assert.deepEqual(patch.body.selfTest.recipeVersions, device);
  }
});
