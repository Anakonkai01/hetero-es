import { InMemoryWebStorage, UserManager, WebStorageStateStore, type UserManagerSettings } from 'oidc-client-ts';
import { configureTokenStorage, setAccessToken } from '../api/token.ts';
import type { RuntimeConfig } from './runtimeConfig.ts';

type OIDCConfig = Extract<RuntimeConfig, { authMode: 'oidc' }>;
type Browser = Pick<Window, 'location' | 'history' | 'sessionStorage' | 'dispatchEvent'>;
let manager: UserManager | undefined;
export function identitySettings(config: OIDCConfig, origin: string, storage: Storage): UserManagerSettings {
  return {
    authority: config.issuer,
    client_id: config.clientId,
    response_type: 'code',
    disablePKCE: false,
    scope: 'openid profile email',
    automaticSilentRenew: true,
    loadUserInfo: false,
    redirect_uri: origin + config.basePath + 'oidc/callback',
    silent_redirect_uri: origin + config.basePath + 'oidc/silent',
    post_logout_redirect_uri: origin + config.basePath + 'oidc/logout',
    userStore: new WebStorageStateStore({ store: new InMemoryWebStorage() }),
    stateStore: new WebStorageStateStore({ store: storage }),
  };
}
export async function initializeIdentity(
  config: RuntimeConfig,
  browser: Browser = window,
  factory: (settings: UserManagerSettings) => UserManager = (settings) => new UserManager(settings),
): Promise<boolean> {
  configureTokenStorage(config.authMode, browser.sessionStorage);
  if (config.authMode === 'local') return true;
  const settings = identitySettings(config, browser.location.origin, browser.sessionStorage);
  manager = factory(settings);
  const identity = manager;
  const publish = (token: string) => {
    setAccessToken(token);
    browser.dispatchEvent(new Event('heteroes-identity-changed'));
  };
  identity.events.addUserLoaded((user) => publish(user.access_token));
  identity.events.addUserUnloaded(() => publish(''));
  identity.events.addAccessTokenExpired(() => publish(''));
  await identity.clearStaleState();
  const path = browser.location.pathname;
  if (path === config.basePath + 'oidc/silent') {
    try {
      await identity.signinSilentCallback(browser.location.href);
    } finally {
      browser.history.replaceState(null, '', config.basePath);
    }
    return false;
  }
  if (path === config.basePath + 'oidc/logout') {
    try {
      await identity.signoutRedirectCallback(browser.location.href);
    } finally {
      await identity.removeUser();
      publish('');
      browser.history.replaceState(null, '', config.basePath + 'login');
    }
    return true;
  }
  if (path === config.basePath + 'oidc/callback') {
    let complete = false;
    try {
      await identity.signinRedirectCallback(browser.location.href);
      complete = true;
    } catch {
      await identity.removeUser();
      publish('');
      throw new Error('Identity sign-in could not complete');
    } finally {
      browser.history.replaceState(null, '', config.basePath + (complete ? 'workspace' : 'login'));
    }
  }
  let user = await identity.getUser();
  if (!user || user.expired) {
    // A reload starts with empty memory. Recover the provider's SSO session without persisting its tokens.
    try {
      user = await identity.signinSilent();
    } catch {
      user = null;
    }
  }
  publish(user && !user.expired ? user.access_token : '');
  return true;
}
export async function signInWithIdentity() {
  if (!manager) throw new Error('Identity sign-in is unavailable');
  await manager.signinRedirect();
}
export async function signOutWithIdentity() {
  if (!manager) throw new Error('Identity sign-in is unavailable');
  manager.stopSilentRenew();
  try {
    await manager.signoutRedirect();
  } catch {
    await manager.removeUser();
    throw new Error('Identity sign-out could not complete');
  }
}
