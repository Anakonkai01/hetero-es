export type RuntimeConfig =
  { authMode: 'local'; basePath: string } | { authMode: 'oidc'; basePath: string; issuer: string; clientId: string };
let config: RuntimeConfig = { authMode: 'local', basePath: '/' };
export function parseRuntimeConfig(value: unknown, defaultBase = '/'): RuntimeConfig {
  if (!value || typeof value !== 'object') throw new Error('Invalid sign-in configuration');
  const input = value as Record<string, unknown>;
  const basePath = input.basePath ?? defaultBase;
  if (typeof basePath !== 'string' || !/^\/(?:[A-Za-z0-9_-]+\/)*$/.test(basePath))
    throw new Error('Invalid application base path');
  if (input.authMode === 'local') return { authMode: 'local', basePath };
  if (input.authMode !== 'oidc' || typeof input.issuer !== 'string') throw new Error('Invalid sign-in configuration');
  const issuer = new URL(input.issuer);
  if (
    !['http:', 'https:'].includes(issuer.protocol) ||
    issuer.username ||
    issuer.password ||
    issuer.search ||
    issuer.hash
  )
    throw new Error('Invalid identity authority');
  const clientId = input.clientId ?? 'heteroes-web';
  if (typeof clientId !== 'string' || !clientId) throw new Error('Invalid identity client');
  return { authMode: 'oidc', basePath, issuer: input.issuer, clientId };
}
export function getRuntimeConfig() {
  return config;
}
export async function loadRuntimeConfig(defaultBase = '/') {
  const response = await fetch('/config.json', { cache: 'no-store', redirect: 'error' });
  if (response.status === 404) config = { authMode: 'local', basePath: defaultBase };
  else {
    if (!response.ok) throw new Error('Sign-in configuration is unavailable');
    config = parseRuntimeConfig(await response.json(), defaultBase);
  }
  return config;
}
