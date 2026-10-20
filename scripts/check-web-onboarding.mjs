/**
 * Browser contract for the first minutes on the website, against a throwaway CPU lab (scripts/serve-test-lab.py):
 * register with a short password, land on Get started with a download, administrator notification, approval.
 *   python3 scripts/serve-test-lab.py --web <built frontend> --port 18080 &
 *   node scripts/check-web-onboarding.mjs http://127.0.0.1:18080 <fresh evidence directory>
 */
import { chromium } from 'playwright';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
const [base, output] = process.argv.slice(2);
if (!base || !output) throw Error('usage: check-web-onboarding.mjs <base url> <fresh evidence directory>');
await fs.mkdir(output, { recursive: true });
const receipt = path.join(output, 'web-onboarding.json');
try {
  await fs.access(receipt);
  throw Error('Evidence already exists');
} catch (error) {
  if (error.code !== 'ENOENT') throw error;
}
const browser = await chromium.launch({ headless: true });
const results = {};
const errors = [];
async function english(page) {
  const select = page.locator('.preference-menu select').first();
  if (!(await select.isVisible())) await page.locator('.preference-menu summary').first().click();
  await select.selectOption('en');
}
try {
  const friend = await (await browser.newContext({ viewport: { width: 1280, height: 900 } })).newPage();
  friend.on('pageerror', (e) => errors.push(e.message));
  await friend.goto(base + '/register');
  await english(friend);
  await friend.getByLabel('Username', { exact: true }).fill('new-friend');
  await friend.getByLabel('Display name', { exact: true }).fill('New Friend');
  // Too short: a clear sentence, no browser bubble, nothing sent.
  await friend.getByLabel('Password', { exact: true }).fill('short7!');
  await friend.getByRole('button', { name: 'Register', exact: true }).click();
  await friend.getByRole('alert').getByText('Use at least 8 characters.').waitFor();
  results.shortPasswordExplained = true;
  // Too common: the server explains.
  await friend.getByLabel('Password', { exact: true }).fill('password123');
  await friend.getByRole('button', { name: 'Register', exact: true }).click();
  await friend.getByRole('alert').getByText('too easy to guess', { exact: false }).waitFor();
  results.commonPasswordExplained = true;
  // Show / hide and the live rule.
  const field = friend.getByLabel('Password', { exact: true });
  await field.fill('x7!kq2mz');
  assert.equal(await field.getAttribute('type'), 'password');
  await friend.getByRole('button', { name: 'Show password' }).click();
  assert.equal(await field.getAttribute('type'), 'text');
  await friend.getByText('✓ At least 8 characters.', { exact: false }).waitFor();
  results.showHideAndRule = true;
  await friend.getByRole('button', { name: 'Register', exact: true }).click();
  await friend.waitForURL('**/get-started');
  results.landsOnGetStarted = true;
  await friend.getByRole('heading', { name: 'Get started' }).waitFor();
  await friend.getByText('Waiting for an administrator to approve your account', { exact: false }).waitFor();
  const windows = friend.getByRole('link', { name: /Download for Windows/ });
  assert.match(await windows.getAttribute('href'), /Windows\.exe$/);
  await friend.getByRole('link', { name: /Download for Linux/ }).waitFor();
  results.downloadVisibleWhilePending = true;
  await friend.getByText(base, { exact: false }).first().waitFor();
  results.labAddressShown = true;
  const nav = friend.getByRole('navigation', { name: 'Main sections' });
  await nav.getByRole('link', { name: 'Home' }).waitFor();
  await nav.getByRole('link', { name: 'Get started' }).waitFor();
  results.navHasHomeAndGetStarted = true;
  const download = await friend.request.get(base + (await windows.getAttribute('href')));
  assert.equal(download.status(), 200);
  results.downloadResponds = true;
  // Headless Linux: one copyable line whose script and bundle both come from this lab.
  const command = `curl -fsSL '${base}/downloads/install-worker.sh' | HETEROES_DOWNLOADS='${base}/downloads' bash`;
  const linux = friend.locator('[data-linux-worker]');
  await linux.getByText(command, { exact: true }).waitFor();
  await linux.getByText(`heteroes-worker join ${base}`, { exact: false }).waitFor();
  assert.equal((await friend.request.get(`${base}/downloads/install-worker.sh`)).status(), 200);
  await friend.setViewportSize({ width: 375, height: 900 });
  assert.equal(await friend.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1), false);
  await friend.setViewportSize({ width: 1280, height: 900 });
  results.linuxCommandShown = true;
  await friend.screenshot({ path: path.join(output, 'get-started.png'), fullPage: true });

  const admin = await (await browser.newContext({ viewport: { width: 1280, height: 900 } })).newPage();
  admin.on('pageerror', (e) => errors.push(e.message));
  await admin.goto(base + '/login');
  await english(admin);
  await admin.getByLabel('Username', { exact: true }).fill('admin');
  await admin.getByLabel('Password', { exact: true }).fill('test-admin-pass');
  await admin.getByRole('button', { name: 'Sign in' }).click();
  await admin.waitForURL('**/workspace');
  await admin.getByText('1 account is waiting for approval.').waitFor({ timeout: 20000 });
  results.adminBannerShown = true;
  await admin.getByRole('status', { name: '1 accounts waiting for approval' }).waitFor();
  results.adminBadgeShown = true;
  // The bell tells the administrator too, in plain words, and the count goes down when it is read.
  const bell = admin.locator('.bell > summary');
  await bell.waitFor();
  await admin.waitForFunction(() => document.querySelector('.bell-badge')?.textContent === '1', null, {
    timeout: 20000,
  });
  results.bellBadge = true;
  await bell.click();
  await admin.getByText('New account request: New Friend (@new-friend)').waitFor();
  results.bellExplainsRequest = true;
  await admin.getByRole('link', { name: /New account request/ }).click();
  await admin.waitForURL('**/operations');
  await admin.waitForFunction(() => !document.querySelector('.bell-badge'), null, { timeout: 20000 });
  results.bellClearsWhenRead = true;
  const card = admin.locator('[data-account="new-friend"]').first();
  await card.getByText('New Friend').waitFor();
  await admin.screenshot({ path: path.join(output, 'approval.png'), fullPage: true });
  await card.getByRole('button', { name: 'Approve' }).click();
  await admin.getByText('New Friend was approved.').waitFor();
  results.approvalConfirmed = true;
  await admin.getByText('No accounts are waiting for approval.').waitFor();
  assert.equal(await admin.getByText('account is waiting for approval.').count(), 0);
  results.bannerClearsAfterApproval = true;
  await friend.reload();
  await friend.getByText('Your account is approved.').waitFor({ timeout: 20000 });
  results.friendSeesApproval = true;
  await friend.locator('.bell > summary').click();
  await friend.getByText('Your account was approved').waitFor({ timeout: 20000 });
  results.friendBellSaysApproved = true;
  // Once approved, the devices page offers the same line next to the pairing code (checked for overflow below).
  await friend.goto(base + '/workers');
  await friend.getByRole('button', { name: '+ Add a GPU computer' }).click();
  await friend.locator('.pairing-panel [data-linux-worker]').getByText(command, { exact: true }).waitFor();
  results.linuxCommandOnDevicesPage = true;
  for (const width of [375, 768, 1280]) {
    for (const page of [friend, admin]) {
      await page.setViewportSize({ width, height: 900 });
      assert.equal(
        await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1),
        false,
        `overflow at ${width}`,
      );
    }
  }
  results.noHorizontalOverflow = true;
  assert.deepEqual(errors, []);
  await fs.writeFile(
    receipt,
    JSON.stringify({ fixtureLab: true, realLab: false, gpuWork: false, ...results, browserErrors: errors }, null, 2) +
      '\n',
    { flag: 'wx' },
  );
  console.log('PASS web onboarding contract (fixture lab, Chromium).');
} finally {
  await browser.close();
}
