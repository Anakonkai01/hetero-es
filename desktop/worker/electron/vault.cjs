const fs = require('node:fs/promises');
const path = require('node:path');
class Vault {
  constructor(root, safeStorage) {
    this.root = root;
    this.storage = safeStorage;
  }
  available() {
    return (
      this.storage.isEncryptionAvailable() &&
      (process.platform === 'win32' || this.storage.getSelectedStorageBackend() !== 'basic_text')
    );
  }
  file(key) {
    if (key !== 'device-token') throw Error('INVALID_VAULT_KEY');
    return path.join(this.root, 'device-token.enc');
  }
  async write(key, value) {
    if (!this.available()) throw Error('SECURE_STORAGE_REQUIRED');
    await fs.mkdir(this.root, { recursive: true, mode: 0o700 });
    await fs.writeFile(this.file(key), this.storage.encryptString(value), { mode: 0o600 });
  }
  async remove(key) {
    await fs.rm(this.file(key), { force: true });
  }
  async read(key) {
    if (!this.available()) throw Error('SECURE_STORAGE_REQUIRED');
    try {
      return this.storage.decryptString(await fs.readFile(this.file(key)));
    } catch (error) {
      if (error.code === 'ENOENT') return null;
      throw Error('DEVICE_CREDENTIAL_UNAVAILABLE');
    }
  }
}
module.exports = { Vault };
