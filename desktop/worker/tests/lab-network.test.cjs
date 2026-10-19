// "The lab did not answer" hid every network problem behind one code. The reason (DNS, certificate, refused, reset,
// timeout) must reach the owner as a specific code and the log as a short line, without the address of the request body.
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const os = require('node:os');
const path = require('node:path');
const { Service, networkCode } = require('../electron/service.cjs');

async function fixture(t, fetch) {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), 'worker-network-'));
  t.after(() => fs.rm(root, { recursive: true, force: true }));
  const logs = [];
  const log = { info: (message, fields) => logs.push({ message, ...fields }), detail() {}, error() {} };
  const service = new Service(
    root,
    root,
    { available: () => true, read: async () => 't', write: async () => {} },
    { log, fetch, setup: { running: false, status: () => ({ installed: false }), paths: () => ({}) } },
  );
  service.settings.serverUrl = 'https://lab.example.org';
  return { service, logs };
}
const failure =
  (code, message = 'fetch failed') =>
  async () => {
    throw new TypeError(message, { cause: Object.assign(Error('inner'), { code }) });
  };

test('system error codes map to specific, owner-readable codes', () => {
  const cases = {
    ENOTFOUND: 'LAB_DNS_FAILED',
    EAI_AGAIN: 'LAB_DNS_FAILED',
    ECONNREFUSED: 'LAB_CONNECTION_REFUSED',
    ECONNRESET: 'LAB_CONNECTION_RESET',
    EPIPE: 'LAB_CONNECTION_RESET',
    UND_ERR_CONNECT_TIMEOUT: 'LAB_TIMEOUT',
    ETIMEDOUT: 'LAB_TIMEOUT',
    EHOSTUNREACH: 'LAB_NETWORK_DOWN',
    ENETUNREACH: 'LAB_NETWORK_DOWN',
    UNABLE_TO_VERIFY_LEAF_SIGNATURE: 'LAB_CERTIFICATE_REJECTED',
    SELF_SIGNED_CERT_IN_CHAIN: 'LAB_CERTIFICATE_REJECTED',
    CERT_HAS_EXPIRED: 'LAB_CERTIFICATE_REJECTED',
    ERR_TLS_CERT_ALTNAME_INVALID: 'LAB_CERTIFICATE_REJECTED',
    DEPTH_ZERO_SELF_SIGNED_CERT: 'LAB_CERTIFICATE_REJECTED',
    UNABLE_TO_GET_ISSUER_CERT_LOCALLY: 'LAB_CERTIFICATE_REJECTED',
  };
  for (const [code, expected] of Object.entries(cases)) assert.equal(networkCode({ cause: { code } }), expected, code);
  assert.equal(networkCode({ code: 'ENOTFOUND' }), 'LAB_DNS_FAILED', 'the code may sit on the error itself');
  assert.equal(networkCode(new Error('offline')), 'LAB_UNREACHABLE', 'unknown failures keep the general code');
  assert.equal(networkCode(undefined), 'LAB_UNREACHABLE');
});

test('a failed request throws the specific code and logs one line with the cause, never the body or the token', async (t) => {
  const { service, logs } = await fixture(t, failure('UNABLE_TO_VERIFY_LEAF_SIGNATURE'));
  await assert.rejects(
    service.api('/api/v1/auth/login', { username: 'u', password: 'hunter2-secret' }, ''),
    /^Error: LAB_CERTIFICATE_REJECTED$/,
  );
  const entry = logs.find((row) => row.message === 'network error');
  assert.equal(entry.code, 'LAB_CERTIFICATE_REJECTED');
  assert.equal(entry.cause, 'UNABLE_TO_VERIFY_LEAF_SIGNATURE');
  assert.equal(entry.host, 'lab.example.org');
  assert.equal(entry.route, '/api/v1/auth/login');
  assert.ok(!JSON.stringify(logs).includes('hunter2'));
});

test('connecting to a lab address reports the same specific code', async (t) => {
  const { service, logs } = await fixture(t, failure('ENOTFOUND'));
  await assert.rejects(service.connect('https://lab.example.org'), /^Error: LAB_DNS_FAILED$/);
  assert.equal(logs.find((row) => row.message === 'network error').route, '/api/v1/health');
});

test('the Connection check shows the specific code for the lab step', async (t) => {
  const { service } = await fixture(t, failure('ECONNRESET'));
  const report = await service.checkConnection();
  assert.deepEqual(
    report.checks.find((c) => c.step === 'lab'),
    { step: 'lab', status: 'FAIL', code: 'LAB_CONNECTION_RESET' },
  );
});

test('a repeated failure is logged once per cause and host, not on every 3 second poll', async (t) => {
  const { service, logs } = await fixture(t, failure('ECONNREFUSED'));
  for (let i = 0; i < 5; i++) await assert.rejects(service.api('/api/v1/health'));
  assert.equal(logs.filter((row) => row.message === 'network error').length, 1);
});

test('a timeout that the app itself enforces stays LAB_TIMEOUT', async (t) => {
  const { service } = await fixture(t, async () => {
    throw Object.assign(Error('aborted'), { name: 'AbortError' });
  });
  await assert.rejects(service.api('/api/v1/health'), /^Error: LAB_TIMEOUT$/);
});
