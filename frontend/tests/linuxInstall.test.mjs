import { test } from 'node:test';
import assert from 'node:assert/strict';
import { linuxInstallCommand } from '../src/lib/linuxInstall.ts';

test('a same-origin installer fetches its bundle from this lab, not the address baked into the script', () => {
  assert.equal(
    linuxInstallCommand('/downloads/install-worker.sh', 'https://lab.example.org'),
    "curl -fsSL 'https://lab.example.org/downloads/install-worker.sh' | " +
      "HETEROES_DOWNLOADS='https://lab.example.org/downloads' bash",
  );
});

test('a private-transfer installer keeps the private address for both downloads', () => {
  assert.equal(
    linuxInstallCommand('http://100.64.0.1:8002/downloads/install-worker.sh', 'https://lab.example.org'),
    "curl -fsSL 'http://100.64.0.1:8002/downloads/install-worker.sh' | " +
      "HETEROES_DOWNLOADS='http://100.64.0.1:8002/downloads' bash",
  );
});

test('an address that could break out of the shell command is never shown', () => {
  for (const url of [
    "/downloads/install-worker.sh'; rm -rf ~; '",
    'javascript:alert(1)',
    'file:///etc/install-worker.sh',
    'ftp://lab.example.org/downloads/install-worker.sh',
    'https://lab.example.org/downloads/install worker.sh',
    '',
  ]) {
    assert.equal(linuxInstallCommand(url, 'https://lab.example.org'), null, url);
  }
});
