/** Candidate14 interaction checks against a disposable loopback fixture lab; no live mutations. */
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import { chromium } from 'playwright';
const [base, out] = process.argv.slice(2);
if (!base || !out || new URL(base).hostname !== '127.0.0.1') throw Error('Use a disposable loopback fixture lab');
await fs.mkdir(out, { recursive: false });
const datasetPrefix = path.basename(out) + ' dataset ';
const browser = await chromium.launch({ headless: true });
const results = { fixtureOnly: true };
try {
  const context = await browser.newContext({ locale: 'en-US', viewport: { width: 1440, height: 1000 } });
  const page = await context.newPage();
  const errors = [];
  page.on('pageerror', (error) => errors.push(error.message));
  await page.goto(base + '/');
  await page.locator('.install-card').waitFor();
  assert.equal(await page.locator('.install-card').count(), 1);
  await page
    .getByRole('group', { name: 'Operating system', exact: true })
    .getByRole('button', { name: 'Linux', exact: true })
    .click();
  assert.equal(await page.locator('[data-linux-worker] details').getAttribute('open'), null);
  await page
    .getByRole('group', { name: 'Operating system', exact: true })
    .getByRole('button', { name: 'Windows', exact: true })
    .click();
  assert.equal(await page.locator('.install-card a[download]').count(), 1);
  results.installChooserHasOnePrimaryAction = true;
  await page.goto(base + '/login');
  await page.locator('input[autocomplete="username"]').fill('admin');
  await page.locator('input[autocomplete="current-password"]').fill('test-admin-pass');
  await page.locator('form button[type="submit"]').click();
  await page.waitForURL((url) => !url.pathname.startsWith('/login'));
  await page.locator('.account-menu summary').click();
  await page.locator('.account-menu').getByRole('link', { name: 'Security', exact: true }).waitFor();
  await page.keyboard.press('Escape');
  assert.equal(await page.locator('.account-menu').getAttribute('open'), null);
  results.accountMenuKeyboard = true;
  await page.goto(base + '/artifacts');
  await page.locator('.artifact-group').first().waitFor();
  assert.equal(await page.locator('.artifact-group [role="row"]').count(), 10);
  await page.getByRole('navigation', { name: 'Pagination' }).getByRole('button', { name: 'Next', exact: true }).click();
  assert.ok((await page.locator('.artifact-group [role="row"]').count()) <= 10);
  const select = page.getByRole('combobox', { name: 'Experiment', exact: true });
  await select.click();
  await page.getByRole('searchbox', { name: 'Search options' }).fill('M3 native');
  await page.keyboard.press('ArrowDown');
  await page.keyboard.press('Enter');
  await page.waitForURL(/experiment=/);
  await page.waitForFunction(() => document.querySelector('#f-ar-e')?.textContent.includes('M3 native'));
  assert.match(await select.innerText(), /M3 native/);
  assert.match(page.url(), /experiment=/);
  results.searchableFilterKeyboard = true;
  const token = await page.evaluate(() => sessionStorage.getItem('heteroes.access-token'));
  const headers = { Authorization: 'Bearer ' + token, 'X-Workspace-Id': 'lab' };
  for (let i = 0; i < 13; i++) {
    const reply = await page.request.post(base + '/api/v1/datasets/import', {
      headers,
      data: {
        recipeVersion: 3,
        name: datasetPrefix + String(i).padStart(2, '0'),
        mapping: { prompt: 'prompt' },
        files: {
          all: {
            format: 'json',
            content: JSON.stringify(Array.from({ length: 20 }, (_, n) => ({ prompt: `fixture ${i} ${n}`, answer: n }))),
          },
        },
      },
    });
    assert.ok(reply.ok(), await reply.text());
  }
  await page.goto(base + '/models');
  await page.getByRole('searchbox', { name: 'Search datasets' }).fill(datasetPrefix);
  assert.equal(await page.locator('.dataset-item').count(), 10);
  await page.getByRole('navigation', { name: 'Pagination' }).getByRole('button', { name: 'Next', exact: true }).click();
  assert.equal(await page.locator('.dataset-item').count(), 3);
  await page.getByRole('searchbox', { name: 'Search datasets' }).fill(datasetPrefix + '12');
  assert.equal(await page.locator('.dataset-item').count(), 1);
  await page
    .locator('summary')
    .filter({ hasText: /^Import dataset$/ })
    .click();
  assert.ok(await page.getByLabel('Dataset name', { exact: true }).isVisible());
  results.datasetPaginationAndSearch = true;
  await page.goto(base + '/operations');
  await page
    .locator('summary')
    .filter({ hasText: /^All accounts/ })
    .click();
  await page.getByText('Your account', { exact: true }).waitFor();
  const own = page.getByText('Your account', { exact: true }).locator('..');
  assert.equal(await own.locator('.more-actions').count(), 0);
  results.selfAdministrationHidden = true;
  for (const width of [375, 768, 1440]) {
    await page.setViewportSize({ width, height: 1000 });
    for (const route of ['/artifacts', '/models', '/operations', '/']) {
      await page.goto(base + route);
      await page.waitForTimeout(500);
      assert.equal(
        await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1),
        false,
        route + ' overflow at ' + width,
      );
      await page.screenshot({
        path: path.join(out, route.replaceAll('/', '') || 'home') + '-' + width + '.png',
        fullPage: true,
      });
    }
  }
  assert.deepEqual(errors, []);
  results.responsiveWithoutOverflow = true;
  await fs.writeFile(path.join(out, 'receipt.json'), JSON.stringify(results, null, 2) + '\n');
  console.log(results);
} finally {
  await browser.close();
}
