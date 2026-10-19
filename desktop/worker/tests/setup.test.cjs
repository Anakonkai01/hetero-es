const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const os = require('node:os');
const path = require('node:path');
const tar = require('tar');
const { extract, run } = require('../electron/setup.cjs');
const { Setup } = require('../electron/setup.cjs');
test(
  'missing selected storage disk fails before creating a fallback runtime',
  { skip: process.platform !== 'linux' },
  async (t) => {
    const root = await fs.mkdtemp(path.join(os.tmpdir(), 'worker-volume-'));
    t.after(() => fs.rm(root, { recursive: true, force: true }));
    await fs.writeFile(
      path.join(root, 'storage.json'),
      JSON.stringify({
        downloads: path.join(root, 'missing-volume/downloads'),
        models: path.join(root, 'missing-volume/models'),
        volumeUUID: '00000000-0000-0000-0000-000000000000',
      }),
    );
    const setup = new Setup(root, path.join(root, 'resources'));
    await assert.rejects(setup.install(), /STORAGE_VOLUME_UNAVAILABLE/);
    assert.equal(setup.status().installed, false);
    await assert.rejects(fs.access(path.join(root, 'runtimes')));
    await assert.rejects(fs.access(path.join(root, 'missing-volume')));
  },
);
test('archive rejects links outside runtime; safe relative symlinks are retained', async (t) => {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), 'worker-extract-'));
  t.after(() => fs.rm(root, { recursive: true, force: true }));
  const src = path.join(root, 'src');
  await fs.mkdir(path.join(src, 'python', 'bin'), { recursive: true });
  await fs.writeFile(path.join(src, 'python', 'bin', 'python3.12'), 'test');
  await fs.symlink('python3.12', path.join(src, 'python', 'bin', 'python3'));
  const file = path.join(root, 'safe.tar.gz');
  await tar.c({ cwd: src, file, gzip: true }, ['python']);
  await extract(file, path.join(root, 'safe'));
  assert.equal(await fs.readFile(path.join(root, 'safe', 'python', 'bin', 'python3'), 'utf8'), 'test');
  await fs.symlink('../../../outside', path.join(src, 'python', 'bin', 'bad'));
  await tar.c({ cwd: src, file: path.join(root, 'bad.tar.gz'), gzip: true }, ['python']);
  await assert.rejects(extract(path.join(root, 'bad.tar.gz'), path.join(root, 'bad')), /UNSAFE/);
});
test('runtime subprocess timeout is bounded and errors omit paths and stderr', async () => {
  await assert.rejects(
    run(process.execPath, ['-e', 'setTimeout(()=>{},10000)'], { timeout: 30 }),
    /RUNTIME_PROCESS_TIMEOUT/,
  );
  await assert.rejects(
    run(process.execPath, ['-e', 'process.stderr.write("private token");process.exit(2)']),
    /^Error: RUNTIME_PROCESS_FAILED$/,
  );
});
test('the READY record names the installed profile, not a fixed one', () => {
  const { readyRecord } = require('../electron/setup.cjs');
  const at = new Date('2026-10-19T00:00:00Z');
  for (const name of ['desktop-v1', 'desktop-v3']) {
    assert.deepEqual(readyRecord({ profile: name, platform: 'windows' }, at), {
      profile: name,
      platform: 'windows',
      verifiedAt: '2026-10-19T00:00:00.000Z',
    });
  }
  assert.throws(() => readyRecord({ platform: 'linux' }, at), /PROFILE_INVALID/);
});
test('a chosen data folder holds runtime, model and downloads in its own subfolder', async (t) => {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), 'worker-data-'));
  t.after(() => fs.rm(root, { recursive: true, force: true }));
  const appData = path.join(root, 'appdata');
  const drive = path.join(root, 'D');
  await fs.mkdir(appData);
  await fs.mkdir(drive);
  await fs.writeFile(path.join(drive, 'keep.txt'), 'user file');
  const setup = new Setup(appData, path.join(root, 'resources'));
  assert.equal(setup.status().dataFolder, appData);
  const chosen = await setup.chooseDataFolder(drive);
  const data = path.join(drive, 'HeteroES-Worker-data');
  assert.equal(chosen.dataFolder, data);
  const storage = JSON.parse(await fs.readFile(path.join(appData, 'storage.json'), 'utf8'));
  assert.deepEqual(storage, {
    runtimes: path.join(data, 'runtimes'),
    models: path.join(data, 'models'),
    downloads: path.join(data, 'downloads'),
    artifacts: path.join(data, 'artifacts'),
  });
  // the uninstaller removes exactly this folder, read from the marker
  assert.equal(await fs.readFile(path.join(appData, 'data-folder.txt'), 'utf8'), data);
  assert.equal(await fs.readFile(path.join(drive, 'keep.txt'), 'utf8'), 'user file');
  const reopened = new Setup(appData, path.join(root, 'resources'));
  assert.equal(reopened.status().dataFolder, data);
  // paths() needs a profile; with one, the runtime lives under the chosen folder
  await fs.mkdir(path.join(root, 'resources'));
  await fs.writeFile(
    path.join(root, 'resources', 'profile.json'),
    JSON.stringify({ platforms: { linux: {}, windows: {} }, modelRevision: 'r', modelFiles: [] }),
  );
  assert.ok(reopened.paths().root.startsWith(path.join(data, 'runtimes') + path.sep));
  assert.ok(reopened.paths().model.startsWith(path.join(data, 'models') + path.sep));
  // an existing folder named relative to the working directory is still refused
  await assert.rejects(setup.chooseDataFolder(path.relative(process.cwd(), drive)), /INVALID_STORAGE_DIRECTORY/);
  await assert.rejects(setup.chooseDataFolder(path.join(root, 'missing')), /INVALID_STORAGE_DIRECTORY/);
  setup.running = true;
  await assert.rejects(setup.chooseDataFolder(drive), /SETUP_IN_PROGRESS/);
});
test('the data folder cannot move once a runtime is installed', async (t) => {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), 'worker-data-'));
  t.after(() => fs.rm(root, { recursive: true, force: true }));
  const setup = new Setup(root, path.join(root, 'resources'));
  setup.status = () => ({ installed: true });
  await assert.rejects(setup.chooseDataFolder(root), /RUNTIME_ALREADY_INSTALLED/);
  await assert.rejects(fs.access(path.join(root, 'storage.json')));
});
