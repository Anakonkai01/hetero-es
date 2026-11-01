import { test } from 'node:test';
import assert from 'node:assert/strict';
import { parseRuntimeConfig } from '../src/app/runtimeConfig.ts';
import { configureTokenStorage, getAccessToken, setAccessToken } from '../src/api/token.ts';
import { initializeIdentity, identitySettings } from '../src/app/identity.ts';

class Storage {
  values = new Map();
  get length() {
    return this.values.size;
  }
  key(i) {
    return [...this.values.keys()][i] ?? null;
  }
  getItem(k) {
    return this.values.get(k) ?? null;
  }
  setItem(k, v) {
    this.values.set(k, String(v));
  }
  removeItem(k) {
    this.values.delete(k);
  }
  clear() {
    this.values.clear();
  }
}
const local = { authMode: 'local', basePath: '/' };
const oidc = {
  authMode: 'oidc',
  basePath: '/lab/',
  issuer: 'https://identity.example.test/realms/lab',
  clientId: 'heteroes-web',
};

test('runtime configuration selects local default and explicit OIDC basename without accepting malformed authority', () => {
  assert.deepEqual(parseRuntimeConfig({ authMode: 'local' }), local);
  assert.deepEqual(parseRuntimeConfig(oidc), oidc);
  for (const bad of [
    { authMode: 'unknown' },
    { ...oidc, issuer: 'https://user:secret@identity.test/' },
    { ...oidc, basePath: '//other/' },
    { ...oidc, basePath: '/../' },
    { authMode: 'oidc' },
  ]) {
    assert.throws(() => parseRuntimeConfig(bad));
  }
});

test('OIDC selection before UI startup clears old local token and never writes tokens to browser storage', () => {
  const storage = new Storage();
  storage.setItem('heteroes.access-token', 'old-local-session');
  configureTokenStorage('local', storage);
  assert.equal(getAccessToken(), 'old-local-session');
  configureTokenStorage('oidc', storage);
  assert.equal(getAccessToken(), '');
  assert.equal(storage.getItem('heteroes.access-token'), null);
  setAccessToken('memory-only-access');
  assert.equal(getAccessToken(), 'memory-only-access');
  assert.equal(storage.length, 0);
  setAccessToken('');
  configureTokenStorage('local', storage);
  setAccessToken('local-session');
  assert.equal(storage.getItem('heteroes.access-token'), 'local-session');
  setAccessToken('');
  assert.equal(storage.length, 0);
});

test('code flow keeps user/refresh tokens in memory and only PKCE transaction state in session storage', async () => {
  const storage = new Storage();
  const settings = identitySettings(oidc, 'http://localhost:18000', storage);
  assert.equal(settings.response_type, 'code');
  assert.equal(settings.disablePKCE, false);
  assert.equal(settings.automaticSilentRenew, true);
  assert.equal(settings.redirect_uri, 'http://localhost:18000/lab/oidc/callback');
  await settings.userStore.set('user', 'private-user-token');
  assert.equal(storage.length, 0);
  await settings.stateStore.set('state', 'pkce-verifier');
  assert.equal(storage.length, 1);
  assert.notEqual(settings.userStore, settings.stateStore);
});

function fakeBrowser(path) {
  const replaced = [];
  return {
    location: {
      origin: 'http://localhost:18000',
      pathname: path,
      href: 'http://localhost:18000' + path + '?code=private-code&state=private-state',
    },
    history: { replaceState: (_a, _b, url) => replaced.push(url) },
    sessionStorage: new Storage(),
    dispatchEvent: () => {},
    replaced,
  };
}
function fakeManager() {
  const handlers = {};
  let user = { access_token: 'renewed-in-memory' };
  return {
    handlers,
    events: {
      addUserLoaded: (f) => (handlers.loaded = f),
      addUserUnloaded: (f) => (handlers.unloaded = f),
      addAccessTokenExpired: (f) => (handlers.expired = f),
    },
    clearStaleState: async () => {},
    getUser: async () => user,
    signinRedirectCallback: async () => user,
    signoutRedirectCallback: async () => {},
    signinSilent: async () => user,
    signinSilentCallback: async () => {},
    removeUser: async () => {
      user = null;
    },
    startSilentRenew: () => {},
    stopSilentRenew: () => {},
  };
}

test('callback is processed before session queries and code/state disappear from the address bar, including failures', async () => {
  const browser = fakeBrowser('/lab/oidc/callback');
  const manager = fakeManager();
  await initializeIdentity(oidc, browser, () => manager);
  assert.equal(getAccessToken(), 'renewed-in-memory');
  assert.deepEqual(browser.replaced, ['/lab/workspace']);
  manager.handlers.loaded({ access_token: 'rotated' });
  assert.equal(getAccessToken(), 'rotated');
  manager.handlers.expired();
  assert.equal(getAccessToken(), '');
  const bad = fakeBrowser('/lab/oidc/callback');
  const failure = fakeManager();
  failure.signinRedirectCallback = async () => {
    throw Error('private-code');
  };
  await assert.rejects(
    initializeIdentity(oidc, bad, () => failure),
    (error) => !error.message.includes('private-code'),
  );
  assert.deepEqual(bad.replaced, ['/lab/login']);
  assert.equal(getAccessToken(), '');
});

test('logout callback clears identity and returns to the base login route', async () => {
  const browser = fakeBrowser('/lab/oidc/logout');
  const manager = fakeManager();
  await initializeIdentity(oidc, browser, () => manager);
  assert.equal(getAccessToken(), '');
  assert.deepEqual(browser.replaced, ['/lab/login']);
});

test('an asynchronous counter read must reach the required value; a resolved Promise is not success', async () => {
  const { waitForCounter } = await import('../../scripts/lib/wait-for-counter.mjs');
  let reads = 0;
  const result = await waitForCounter(async () => ({ refreshGrants: ++reads >= 3 ? 1 : 0 }), 'refreshGrants', 1, {
    timeout: 1000,
    interval: 1,
  });
  assert.ok(reads >= 3);
  assert.equal(result.refreshGrants, 1);
  await assert.rejects(
    waitForCounter(async () => ({ refreshGrants: 0 }), 'refreshGrants', 1, { timeout: 5, interval: 1 }),
  );
  await assert.rejects(waitForCounter(async () => ({}), 'refreshGrants', 1, { timeout: 5, interval: 1 }));
});
