// Removing the Worker must remove what it stored (pairing, credential, runtime, logs); removing the Lab Server must
// never remove the lab's database. These are the settings the Windows uninstaller reads.
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const worker = require('../package.json');
const server = require('../../server/package.json');

test('uninstalling the Worker deletes its app data; uninstalling the Lab Server does not', () => {
  assert.equal(worker.build.nsis.deleteAppDataOnUninstall, true);
  assert.equal(server.build.nsis.deleteAppDataOnUninstall, false);
});

test('the Worker uninstall script removes its own folder and the parent only when empty, and keeps data on an upgrade', () => {
  const script = fs.readFileSync(path.join(__dirname, '../build/installer.nsh'), 'utf8');
  assert.match(script, /customUnInstall/);
  assert.match(script, /\$\{ifNot\} \$\{isUpdated\}/);
  assert.match(script, /RMDir \/r "\$APPDATA\\@heteroes\\worker"/);
  assert.match(
    script,
    /^\s*RMDir "\$APPDATA\\@heteroes"\s*$/m,
    'the parent is removed without /r, so a Lab Server next to it is safe',
  );
  assert.doesNotMatch(script, /RMDir \/r "\$APPDATA\\@heteroes"/);
});

test('the folder the script removes is the folder the app really uses', () => {
  // Electron derives userData from the package name; "@heteroes/worker" becomes @heteroes\worker on Windows.
  assert.equal(worker.name, '@heteroes/worker');
  assert.equal(worker.name.replace(/\//g, '\\'), '@heteroes\\worker');
});
