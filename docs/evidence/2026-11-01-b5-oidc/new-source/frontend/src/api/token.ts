/** Token persistence is selected before any session request. OIDC never reads/writes a token in browser storage. */
const TOKEN_KEY = 'heteroes.access-token';
let accessToken = '';
let persistentStorage: Storage | undefined;
export function configureTokenStorage(mode: 'local' | 'oidc', storage: Storage) {
  persistentStorage = mode === 'local' ? storage : undefined;
  accessToken = mode === 'local' ? (storage.getItem(TOKEN_KEY) ?? '') : '';
  if (mode === 'oidc') storage.removeItem(TOKEN_KEY);
}
export function getAccessToken() {
  return accessToken;
}
export function setAccessToken(token: string) {
  accessToken = token;
  if (token) persistentStorage?.setItem(TOKEN_KEY, token);
  else persistentStorage?.removeItem(TOKEN_KEY);
}
