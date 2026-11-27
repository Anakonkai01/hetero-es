const { test } = require('node:test');
const assert = require('node:assert/strict');
const { agentEnv } = require('../electron/agent-env.cjs');
const python = 'C:\\Users\\a\\AppData\\Roaming\\HeteroES Worker\\runtimes\\abc\\python\\python.exe';
const bin =
  'C:\\Users\\a\\AppData\\Roaming\\HeteroES Worker\\runtimes\\abc\\python\\Lib\\site-packages\\nvidia\\cu13\\bin';
test('a packaged Python child ignores the user site and gets the runtime source', () => {
  const env = agentEnv('/r/python/bin/python3.12', '/r/src', { HOME: '/h', PATH: '/usr/bin' }, 'linux');
  assert.deepEqual(env, {
    HOME: '/h',
    PATH: '/usr/bin',
    PYTHONPATH: '/r/src',
    PYTHONNOUSERSITE: '1',
    PYTHONUTF8: '1',
  });
});
test('on Windows the pinned CUDA tools folder comes first on the inherited Path, whatever its spelling', () => {
  const env = agentEnv(python, 'C:\\src', { Path: 'C:\\Windows\\system32' }, 'win32');
  assert.equal(env.Path, bin + ';C:\\Windows\\system32');
  assert.equal(env.PATH, undefined); // a second PATH entry would leave Windows with two conflicting values
  assert.equal(agentEnv(python, 'C:\\src', { PATH: 'C:\\x' }, 'win32').PATH, bin + ';C:\\x');
  assert.equal(agentEnv(python, 'C:\\src', {}, 'win32').Path, bin);
  const lower = agentEnv(python, 'C:\\src', { path: 'C:\\y' }, 'win32');
  assert.deepEqual([lower.path, lower.Path], [bin + ';C:\\y', undefined]);
});
test('the inherited environment object is not changed', () => {
  const base = { Path: 'C:\\x' };
  agentEnv(python, 'C:\\src', base, 'win32');
  assert.deepEqual(base, { Path: 'C:\\x' });
});
// The Bridge and the self-test start Python on Windows with this environment (both read process.platform when they run).
function onWindows(t) {
  const real = Object.getOwnPropertyDescriptor(process, 'platform');
  Object.defineProperty(process, 'platform', { value: 'win32' });
  t.after(() => Object.defineProperty(process, 'platform', real));
}
test('the agent bridge starts its Python with the agent environment', (t) => {
  const childProcess = require('node:child_process');
  const { EventEmitter } = require('node:events');
  const realSpawn = childProcess.spawn;
  const calls = [];
  childProcess.spawn = (program, args, options) => {
    calls.push({ program, args, options });
    const child = new EventEmitter();
    child.stdout = new EventEmitter();
    child.stderr = new EventEmitter();
    child.stdin = Object.assign(new EventEmitter(), { write: () => true });
    return child;
  };
  t.after(() => (childProcess.spawn = realSpawn));
  onWindows(t);
  const { Bridge } = require('../electron/bridge.cjs');
  const bridge = new Bridge(python, 'C:\\src', {}, 'token');
  bridge.ready.catch(() => {});
  for (const request of bridge.pending.values()) clearTimeout(request.timeout);
  assert.equal(calls.length, 1);
  assert.deepEqual(calls[0].options.env, agentEnv(python, 'C:\\src', process.env, 'win32'));
});
test('the self-test starts its Python with the agent environment', async (t) => {
  const shared = require('@heteroes/desktop-shared/runtime.cjs');
  const realRun = shared.run;
  const calls = [];
  shared.run = async (program, args, options) => {
    calls.push({ program, options });
    options.onLine(JSON.stringify({ result: { ok: true } }) + '\n');
  };
  t.after(() => (shared.run = realRun));
  onWindows(t);
  const fs = require('node:fs/promises');
  const os = require('node:os');
  const path = require('node:path');
  const root = await fs.mkdtemp(path.join(os.tmpdir(), 'worker-agent-env-'));
  t.after(() => fs.rm(root, { recursive: true, force: true }));
  const profile = { profile: 'desktop-v3', modelRevision: 'r', modelFiles: [], platforms: { windows: {}, linux: {} } };
  await fs.writeFile(path.join(root, 'profile.json'), JSON.stringify(profile));
  const { Setup } = require('../electron/setup.cjs');
  const setup = new Setup(root, root);
  setup.status = () => ({ installed: true });
  assert.deepEqual(await setup.selfTest(), { ok: true });
  const p = setup.paths();
  assert.equal(calls[0].program, p.python);
  assert.deepEqual(calls[0].options.env, agentEnv(p.python, p.source, process.env, 'win32'));
});
