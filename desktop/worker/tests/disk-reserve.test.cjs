// Installing must leave FREE_SPACE_RESERVE_BYTES free on every drive it writes to, for both apps.
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { FREE_SPACE_RESERVE_BYTES, leavesReserve } = require('@heteroes/desktop-shared/disk.cjs');
const GiB = 1024 ** 3;
const profile = {
  profile: 'desktop-v3',
  modelRevision: 'r',
  runtimeSha256: '0'.repeat(64),
  // nothing listens on port 9: past the disk check the install fails at its first download instead
  modelFiles: [{ name: 'model.safetensors', url: 'http://127.0.0.1:9/m', sha256: '0'.repeat(64), sizeBytes: GiB }],
  platforms: Object.fromEntries(
    ['linux', 'windows'].map((p) => [
      p,
      {
        python: { name: 'python.tar.gz', url: 'http://127.0.0.1:9/p', sha256: '0'.repeat(64), sizeBytes: GiB },
        wheels: [{ name: 'w.whl', url: 'http://127.0.0.1:9/w', sha256: '0'.repeat(64), sizeBytes: GiB }],
        lockFile: 'lock.txt',
      },
    ]),
  ),
};
function withFreeBytes(t, free) {
  const real = fs.promises.statfs;
  fs.promises.statfs = async () => ({ bavail: free, bsize: 1 });
  t.after(() => (fs.promises.statfs = real));
}
async function folders(t) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'disk-reserve-'));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  fs.mkdirSync(path.join(root, 'resources'));
  fs.writeFileSync(path.join(root, 'resources', 'profile.json'), JSON.stringify(profile));
  return { data: path.join(root, 'data'), resources: path.join(root, 'resources') };
}
async function installError(t, App, free) {
  withFreeBytes(t, free);
  const { data, resources } = await folders(t);
  return new App(data, resources).install().then(
    () => 'installed',
    (error) => error.message,
  );
}
test('the reserve is exact', () => {
  assert.equal(FREE_SPACE_RESERVE_BYTES, 5 * GiB);
  assert.equal(leavesReserve(10 * GiB, 5 * GiB), true);
  assert.equal(leavesReserve(10 * GiB - 1, 5 * GiB), false);
});
// Worker: all folders on one drive need runtime x2 + 512 MiB, downloads = runtime, and the model (here 2+2+0.5+2+1 GiB).
const workerNeed = 2 * GiB * 2 + 512 * 1024 ** 2 + 2 * GiB + GiB;
test('the Worker refuses an install that would leave less than the reserve', async (t) => {
  const { Setup } = require('../electron/setup.cjs');
  assert.equal(await installError(t, Setup, workerNeed + FREE_SPACE_RESERVE_BYTES - 1), 'INSUFFICIENT_DISK_SPACE');
});
test('the Worker goes past the disk check when the reserve stays free', async (t) => {
  const { Setup } = require('../electron/setup.cjs');
  const error = await installError(t, Setup, workerNeed + FREE_SPACE_RESERVE_BYTES);
  assert.notEqual(error, 'INSUFFICIENT_DISK_SPACE');
  assert.notEqual(error, 'installed');
});
// Lab Server: runtime x4 + 256 MiB (here 8.25 GiB).
const serverNeed = 2 * GiB * 4 + 256 * 1024 ** 2;
test('the Lab Server refuses an install that would leave less than the reserve', async (t) => {
  const { Setup } = require('../../server/electron/setup.cjs');
  assert.equal(await installError(t, Setup, serverNeed + FREE_SPACE_RESERVE_BYTES - 1), 'INSUFFICIENT_DISK_SPACE');
  const error = await installError(t, Setup, serverNeed + FREE_SPACE_RESERVE_BYTES);
  assert.notEqual(error, 'INSUFFICIENT_DISK_SPACE');
});
test('the data folder is shown normalized', async (t) => {
  const { Setup } = require('../electron/setup.cjs');
  const { data, resources } = await folders(t);
  fs.mkdirSync(data);
  assert.equal(
    new Setup(data + path.sep + '.' + path.sep, resources).status().dataFolder,
    path.normalize(data + path.sep),
  );
});
