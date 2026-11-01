#!/usr/bin/env node
/** Actual browser Code+PKCE/refresh/logout against an ephemeral protocol fixture, not a deployed Keycloak claim. */
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { mkdir, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { chromium } from 'playwright';
import { waitForCounter } from './lib/wait-for-counter.mjs';
const out = path.resolve(process.argv[2] ?? '.scratch/web-oidc');
await mkdir(out, { recursive: true });
const child = spawn(process.env.PYTHON ?? '.venv-backend/bin/python', ['scripts/serve-test-oidc.py'], {
  env: { ...process.env, CUDA_VISIBLE_DEVICES: '' },
  stdio: ['ignore', 'pipe', 'pipe'],
});
let browser;
let phase = 'fixture startup';
const checks = [];
let storageDiagnostics;
try {
  const origin = await new Promise((resolve, reject) => {
    let buffer = '';
    const timeout = setTimeout(() => reject(new Error('Fixture startup timeout')), 15000);
    child.once('exit', () => {
      clearTimeout(timeout);
      reject(new Error('Fixture stopped'));
    });
    child.stdout.on('data', (chunk) => {
      buffer += chunk;
      const line = buffer.split('\n').find((l) => l.startsWith('{'));
      if (line) {
        clearTimeout(timeout);
        resolve(JSON.parse(line).origin);
      }
    });
  });
  for (let i = 0; i < 100; i++) {
    if (
      await fetch(origin + '/healthz')
        .then((r) => r.ok)
        .catch(() => false)
    )
      break;
    await new Promise((resolve) => setTimeout(resolve, 100));
  }
  browser = await chromium.launch({ headless: true });
  const context = await browser.newContext();
  const page = await context.newPage();
  await page.addInitScript(() => {
    // A single legacy session seed. Iframe/about:blank navigations must not inject a new token after startup.
    if (!sessionStorage.getItem('fixture.local-session-seeded')) {
      sessionStorage.setItem('heteroes.access-token', 'old-local-session-must-disappear');
      sessionStorage.setItem('fixture.local-session-seeded', '1');
    }
  });
  phase = 'identity login UI';
  await page.goto(origin + '/lab/login');
  await page.getByRole('button', { name: /Sign in with HeteroES ID|Đăng nhập bằng HeteroES ID/ }).waitFor();
  assert.equal(await page.locator('input[type=password]').count(), 0);
  checks.push('OIDC UI has identity login and no local password form');
  await page.getByRole('button', { name: /Sign in with HeteroES ID|Đăng nhập bằng HeteroES ID/ }).click();
  phase = 'provider approval UI';
  await page.getByRole('button', { name: 'Approve fixture identity' }).click();
  phase = 'authorization code callback';
  await page.waitForURL(origin + '/lab/workspace');
  phase = 'signed-in account UI';
  await page
    .locator('summary[aria-label]')
    .filter({ has: page.locator('.account-name') })
    .waitFor();
  assert.equal(new URL(page.url()).search, '');
  checks.push('real library Code+PKCE returns to /lab with callback query erased');
  async function assertPrivateStorage() {
    const clean = await page.evaluate(() => {
      const values = [...Object.values(sessionStorage), ...Object.values(localStorage)];
      return (
        sessionStorage.getItem('heteroes.access-token') === null &&
        values.every(
          (v) => !v.includes('access_token') && !v.includes('refresh_token') && !/^eyJ[\w-]+\.[\w-]+\.[\w-]+$/.test(v),
        )
      );
    });
    if (!clean)
      storageDiagnostics = await page.evaluate(() => {
        const values = [...Object.values(sessionStorage), ...Object.values(localStorage)];
        return {
          localKeyPresent: sessionStorage.getItem('heteroes.access-token') !== null,
          accessField: values.some((v) => v.includes('access_token')),
          refreshField: values.some((v) => v.includes('refresh_token')),
          jwtValue: values.some((v) => /^eyJ[\w-]+\.[\w-]+\.[\w-]+$/.test(v)),
        };
      });
    assert.equal(clean, true);
  }
  await assertPrivateStorage();
  checks.push('access/refresh tokens absent from localStorage and sessionStorage');
  phase = 'automatic refresh';
  await waitForCounter(() => fetch(origin + '/fixture-receipt').then((r) => r.json()), 'refreshGrants', 1);
  await assertPrivateStorage();
  checks.push('automatic silent renewal uses a real refresh grant');
  await page.screenshot({ path: path.join(out, 'signed-in.png'), fullPage: true });
  phase = 'memory-only SSO reload';
  await page.reload();
  await page
    .locator('summary')
    .filter({ has: page.locator('.account-name') })
    .waitFor();
  await assertPrivateStorage();
  checks.push('page reload recovers SSO through code flow without persisting tokens');
  phase = 'provider logout';
  await page
    .locator('summary')
    .filter({ has: page.locator('.account-name') })
    .click();
  await page
    .getByRole('button', { name: /Sign out|Đăng xuất/ })
    .first()
    .click();
  await page.waitForURL(origin + '/lab/login');
  await page.getByRole('button', { name: /Sign in with HeteroES ID|Đăng nhập bằng HeteroES ID/ }).waitFor();
  await assertPrivateStorage();
  checks.push('end-session logout returns to clean /lab/login');
  const receipt = await fetch(origin + '/fixture-receipt').then((r) => r.json());
  assert.ok(receipt.refreshGrants >= 1);
  assert.equal(receipt.pkceVerified, true);
  assert.ok(receipt.codeGrants >= 2);
  assert.equal(receipt.logouts, 1);
  await writeFile(
    path.join(out, 'receipt.json'),
    JSON.stringify(
      { scope: 'real browser OIDC protocol fixture; not Keycloak deployment', checks, provider: receipt },
      null,
      2,
    ) + '\n',
  );
  console.log(
    'PASS OIDC browser:',
    checks.length,
    'contracts; Code+PKCE, memory tokens, actual renewal, provider logout',
  );
} catch (error) {
  await writeFile(
    path.join(out, 'failure.json'),
    JSON.stringify({ phase, errorType: error.name, checks, storageDiagnostics }, null, 2) + '\n',
  );
  console.error('FAIL OIDC browser phase:', phase, 'error type:', error.name);
  process.exitCode = 1;
} finally {
  await browser?.close();
  child.kill('SIGTERM');
  if (child.exitCode === null)
    await new Promise((resolve) => {
      const timer = setTimeout(() => {
        child.kill('SIGKILL');
        resolve();
      }, 5000);
      child.once('exit', () => {
        clearTimeout(timer);
        resolve();
      });
    });
}
