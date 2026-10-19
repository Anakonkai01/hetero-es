const { test } = require('node:test');
const assert = require('node:assert/strict');
const { Vault } = require('../electron/vault.cjs');
test('Linux plaintext fallback cannot persist device credentials', { skip: process.platform !== 'linux' }, async () => {
  const vault = new Vault('/unused', {
    isEncryptionAvailable: () => true,
    getSelectedStorageBackend: () => 'basic_text',
  });
  assert.equal(vault.available(), false);
  await assert.rejects(vault.write('device-token', 'secret'), /SECURE_STORAGE_REQUIRED/);
});
