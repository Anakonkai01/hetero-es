/** Real packaged Electron + isolated pinned Python. No development source imports. */
const { _electron: electron } = require('playwright');
const fs = require('node:fs/promises');
const path = require('node:path');
const os = require('node:os');
const crypto = require('node:crypto');
const { spawnSync } = require('node:child_process');
const assert = require('node:assert/strict');

function argument(name) {
  const index = process.argv.indexOf(name);
  return index < 0 ? undefined : process.argv[index + 1];
}
const phase = argument('--phase') ?? 'install';
const gpu = phase === 'qualify';
if (!['install', 'qualify'].includes(phase)) throw Error('Unsupported phase');
if (gpu && !(process.argv.includes('--gpu') && process.env.HETEROES_GPU_ACCEPTANCE === '1'))
  throw Error('GPU acceptance needs --gpu and HETEROES_GPU_ACCEPTANCE=1');
const executable = argument('--executable');
const output = argument('--output');
if (!executable || !output || !process.env.XDG_CONFIG_HOME || !process.env.XDG_DATA_HOME)
  throw Error('Explicit executable, output and isolated XDG directories required');

(async () => {
  await fs.mkdir(output, { recursive: true, mode: 0o700 });
  const evidence = path.join(output, 'packaged-linux-' + phase + '.json');
  try {
    await fs.access(evidence);
    throw Error('Existing acceptance evidence is never overwritten');
  } catch (e) {
    if (e.code !== 'ENOENT') throw e;
  }
  const privateRoot = path.join(os.homedir(), '.config/heteroes-private/linux-worker-proof');
  await fs.mkdir(privateRoot, { recursive: true, mode: 0o700 });
  const key = path.join(privateRoot, 'keyring-test-password');
  try {
    await fs.writeFile(key, crypto.randomBytes(32).toString('base64'), { flag: 'wx', mode: 0o600 });
  } catch (e) {
    if (e.code !== 'EEXIST') throw e;
  }
  const control = path.join(privateRoot, 'keyring-control');
  await fs.mkdir(control, { recursive: true, mode: 0o700 });
  const daemon = spawnSync(
    'gnome-keyring-daemon',
    ['--unlock', '--components=secrets', '--control-directory=' + control],
    { input: await fs.readFile(key), timeout: 10000, encoding: 'utf8' },
  );
  if (daemon.status !== 0) throw Error('Isolated keyring could not unlock');
  const env = {
    ...process.env,
    GNOME_KEYRING_CONTROL: control,
    XDG_CURRENT_DESKTOP: 'GNOME',
    PYTHONNOUSERSITE: '1',
    PYTHONUTF8: '1',
  };
  if (!gpu) env.CUDA_VISIBLE_DEVICES = '';
  let app;
  const launch = () =>
    electron.launch({
      executablePath: path.resolve(executable),
      args: ['--disable-gpu', '--password-store=gnome-libsecret'],
      env,
      timeout: 30000,
    });
  const invoke = (page, action, args = {}) =>
    page.evaluate(
      async ({ action, args }) => {
        const reply = await window.worker.call(action, args);
        if (!reply.ok) throw Error(reply.error);
        return reply.result;
      },
      { action, args },
    );
  try {
    app = await launch();
    await app.firstWindow();
    const observed = await app.evaluate(({ app, safeStorage }) => {
      const cipher = safeStorage.encryptString('heteroes-keyring-roundtrip');
      return {
        packaged: app.isPackaged,
        version: app.getVersion(),
        userData: app.getPath('userData'),
        encrypted: safeStorage.isEncryptionAvailable(),
        backend: safeStorage.getSelectedStorageBackend(),
        roundtrip: safeStorage.decryptString(cipher) === 'heteroes-keyring-roundtrip',
      };
    });
    assert.equal(observed.packaged, true);
    assert.equal(observed.encrypted, true);
    assert.notEqual(observed.backend, 'basic_text');
    assert.equal(observed.roundtrip, true);
    assert.ok(observed.userData.startsWith(path.resolve(process.env.XDG_CONFIG_HOME) + path.sep));
    if (!gpu) {
      await app.close();
      app = null;
      await fs.writeFile(
        path.join(observed.userData, 'storage.json'),
        JSON.stringify({
          downloads: '/mnt/Archive-2tb/heteroes-local/downloads/worker-v1',
          models: '/mnt/Archive-2tb/heteroes-local/models',
          volumeUUID: '10443D1F443D094C',
        }),
        { mode: 0o600 },
      );
      app = await launch();
    }
    const page = await app.firstWindow();
    const before = await invoke(page, 'status');
    assert.equal(before.device, null);
    assert.equal(before.agent, null);
    if (gpu) {
      assert.equal(before.setup.installed, true);
    } else {
      assert.equal(before.setup.installed, false);
    }
    console.log('Packaged Linux ' + phase + ' started; secure backend ' + observed.backend);
    const started = Date.now();
    if (gpu) {
      const result = await invoke(page, 'selftest');
      assert.equal(result.passed, true);
      assert.equal(result.compatibility.repeatIdentical, true);
      assert.ok(result.gpuUUID?.startsWith('GPU-'));
      observed.selfTest = result;
    } else {
      const result = await invoke(page, 'install');
      assert.equal(result.installed, true);
    }
    const after = await invoke(page, 'status');
    assert.equal(after.device, null);
    assert.equal(after.agent, null);
    await app.evaluate(({ BrowserWindow }) => BrowserWindow.getAllWindows()[0].close());
    assert.equal(await app.evaluate(({ BrowserWindow }) => BrowserWindow.getAllWindows()[0].isVisible()), false);
    const record = {
      phase,
      actualPackagedApp: true,
      freshIsolatedRuntime: !gpu,
      sharedVerifiedDownloadCache: true,
      gpuWork: gpu,
      displayEnvironment: 'Xvfb; isolated D-Bus and real GNOME libsecret keyring',
      ordinaryOwnerDesktopWalkthrough: false,
      elapsedSeconds: (Date.now() - started) / 1000,
      closeToTray: true,
      unenrolledAndOff: true,
      ...observed,
    };
    await fs.writeFile(evidence, JSON.stringify(record, null, 2) + '\n', { flag: 'wx', mode: 0o600 });
    console.log('PASS packaged Linux ' + phase + '; evidence saved without credentials.');
  } finally {
    if (app) await app.close();
  }
})().catch((e) => {
  console.error(e.message);
  process.exitCode = 1;
});
